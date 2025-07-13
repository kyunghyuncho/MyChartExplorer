import Foundation

// NOTE: These response structs are identical to your original ones and can be shared.
struct CategoriesResponse: Decodable { let categories: [String] }
struct QueriesResponse: Decodable { let queries: [String] }


struct OllamaService : AdvisingService {
    private let model: String
    private let host: String
    private let apiURL: URL
    
    init(model: String = "gemma3:4b-it-qat",
         host: String = "http://localhost:11434") {
        self.model = model
        self.host = host
        // We can safely force-unwrap here since the host is a known valid URL structure.
        self.apiURL = URL(string: "\(host)/api/generate")!
    }

    // MARK: - Private API Request Handlers

    /// Generic helper for requests that expect a JSON object in the response.
    private func makeAPIRequest<T: Decodable>(prompt: String) async throws -> T {
        var request = URLRequest(url: apiURL)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")

        // Create the payload for the Ollama API with JSON format enabled.
        let payload = OllamaRequestPayload(model: self.model, prompt: prompt, format: "json")
        request.httpBody = try JSONEncoder().encode(payload)
        
        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
        
        // First, decode the main Ollama response wrapper.
        let ollamaResponse = try JSONDecoder().decode(OllamaAPIResponse.self, from: data)
        
        // The actual content is a string inside the 'response' key. Convert it back to Data.
        guard let responseStringData = ollamaResponse.response.data(using: .utf8) else {
            throw URLError(.cannotParseResponse)
        }
        
        // Now, decode the nested JSON string into the target type <T>.
        return try JSONDecoder().decode(T.self, from: responseStringData)
    }

    /// Helper for requests that expect a plain text string in the response.
    private func makeTextAPIRequest(prompt: String) async throws -> String {
        var request = URLRequest(url: apiURL)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")

        // Create the payload for the Ollama API for a plain text response.
        let payload = OllamaRequestPayload(model: self.model, prompt: prompt)
        request.httpBody = try JSONEncoder().encode(payload)

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }

        let ollamaResponse = try JSONDecoder().decode(OllamaAPIResponse.self, from: data)
        return ollamaResponse.response
    }
    
    // MARK: - Public Service Methods

    func getRelevantCategories(symptoms: String, schema: String) async throws -> [String] {
        let prompt = """
        A user is reporting the following symptoms: "\(symptoms)".
        Based on these symptoms, what categories of medical information would be most relevant to retrieve from their personal health record?
        The available tables and their schemas are:
        \(schema)
        
        Please respond with a JSON object containing a single key "categories" which is a list of strings. Each string should be a brief, user-friendly description of a relevant data category.
        For example: ["Recent blood pressure readings", "Current active medications", "History of surgeries related to the abdomen", "Recent clinical notes mentioning headaches"].
        """
        // The <T> type is inferred by the compiler from the return type of this function.
        let response: CategoriesResponse = try await makeAPIRequest(prompt: prompt)
        
        print("Retrieved categories (Ollama): \(response.categories)")
        
        return response.categories
    }
    
    func getSQLQueries(categories: [String], schema: String) async throws -> [String] {
        let prompt = """
        Based on the need for the following information categories: \(categories),
        and the following database schema:
        \(schema)
        
        **IMPORTANT**: Strictly stick to the schema provided. Do not assume any additional columns or tables. Everyone's life depends on it.
        
        Generate the SQLite3 queries required to retrieve this information.
        **IMPORTANT**: The queries must be very specific to retrieve only the minimal necessary data. Do NOT use `SELECT *`. Select only the specific columns needed. For any query on a table that has a `patientId` column, you **MUST** include `WHERE patientId = ?` in the query. For the `notes` table, use `WHERE noteContent LIKE '%symptom%'` to find relevant notes. Use other `WHERE` clauses with dates or other conditions to further narrow down results where appropriate.
        
        Please respond with a JSON object containing a single key "queries" which is a list of strings, where each string is a single, valid SQLite3 query.
        Example of a good specific query: "SELECT medicationName, startDate FROM medications WHERE patientId = ? AND status = 'active' ORDER BY startDate DESC LIMIT 5;"
        """
        let response: QueriesResponse = try await makeAPIRequest(prompt: prompt)
        
        print("Generated SQL queries (Ollama): \(response.queries)")
        
        return response.queries
    }
    
    func getFinalAdvice(symptoms: String, context: String) async throws -> String {
        let prompt = """
        You are a helpful and cautious AI medical assistant. A user has provided their symptoms and relevant data from their medical record.
        Your task is to provide a helpful, structured, and safe response.
        
        Here is the information:
        
        SYMPTOMS REPORTED BY USER:
        "\(symptoms)"
        
        RELEVANT MEDICAL DATA RETRIEVED FROM USER'S RECORD:
        ---
        \(context)
        ---
        
        Based on all of this information, please provide a helpful analysis and potential next steps for the user. Structure your response using Markdown with headers, bold text, and lists to make it easy to read. Do not ask for more information, provide a complete response based on what is given.
        """
        return try await makeTextAPIRequest(prompt: prompt)
    }
    
    // MARK: - New Per-Note Summarizer
    
    func summarize(note: String, symptoms: String) async throws -> String {
        let prompt = """
        A user has the following symptoms: "\(symptoms)".
        Summarize the following clinical note concisely, focusing only on details relevant to these symptoms.

        NOTE:
        "\(note)"
        """
        // This uses your existing helper for plain text API calls
        return try await makeTextAPIRequest(prompt: prompt)
    }

    // MARK: - Reworked Processing Logic

    func processDBResults(results: String, symptoms: String) async throws -> ProcessedDBResult {
        print("🤖 Processing DB results with per-note summarization (Ollama)...")
        
        // Split the raw string into separate query results
        let allQuerySections = results.components(separatedBy: "--- Query:")
                                      .filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        
        var fullContextBuilder = ""
        var notesForDisplayBuilder = ""

        // Process each query result section
        for section in allQuerySections {
            let sectionTitle = "--- Query:" + section.lines.first!
            let isNotesSection = section.lowercased().contains("notes") && section.lowercased().contains("notecontent")

            if !isNotesSection {
                // If it's not a notes section, add it only to the full context
                fullContextBuilder.append(sectionTitle + "\n" + section.lines.dropFirst().joined(separator: "\n") + "\n\n")
            } else {
                // If it IS a notes section, process it line by line
                print("Found notes section. Summarizing each note...")
                let lines = section.lines
                guard lines.count > 1 else { continue }
                
                let header = lines[1] // e.g., "note_date | note_type | note_content"
                let contentColumnIndex = header.components(separatedBy: "|").firstIndex(where: { $0.trimmingCharacters(in: .whitespaces) == "note_content" }) ?? -1

                // Add the header to both builders
                fullContextBuilder.append(sectionTitle + "\n" + header + "\n")
                notesForDisplayBuilder.append(sectionTitle + "\n" + header + "\n")

                // Loop through data rows, starting from the third line
                for rowString in lines.dropFirst(2) {
                    var columns = rowString.components(separatedBy: "|")
                    
                    if contentColumnIndex != -1 && columns.indices.contains(contentColumnIndex) {
                        let originalNote = columns[contentColumnIndex]
                        
                        // Call the new summarize function for each note
                        let summary = try await summarize(note: originalNote, symptoms: symptoms)
                        
                        // Replace the original note with "[Summary] ..."
                        columns[contentColumnIndex] = " [Summary] \(summary)"
                        
                        // Rebuild the row string
                        let summarizedRow = columns.joined(separator: "|")
                        fullContextBuilder.append(summarizedRow + "\n")
                        notesForDisplayBuilder.append(summarizedRow + "\n")
                    } else {
                        // If there's no note content, just append the original row
                        fullContextBuilder.append(rowString + "\n")
                    }
                }
                fullContextBuilder.append("\n")
                notesForDisplayBuilder.append("\n")
            }
        }
        
        print("✅ DB results processed.")

        return ProcessedDBResult(
            fullContext: fullContextBuilder,
            notesForDisplay: notesForDisplayBuilder.isEmpty ? "No relevant notes found." : notesForDisplayBuilder
        )
    }
}

// MARK: - Helper Structs for Ollama API

/// The JSON payload to be sent in the body of the request to Ollama.
private struct OllamaRequestPayload: Codable {
    let model: String
    let prompt: String
    let stream: Bool = false // We want the full response at once
    var format: String? = nil // Set to "json" to enforce JSON output
}

/// The top-level JSON response from the Ollama API.
private struct OllamaAPIResponse: Decodable {
    /// The actual text or JSON string generated by the model.
    let response: String
    let model: String
    let createdAt: String
    let done: Bool

    // Maps Ollama's 'created_at' key to Swift's 'createdAt' property.
    enum CodingKeys: String, CodingKey {
        case response, model, done
        case createdAt = "created_at"
    }
}
