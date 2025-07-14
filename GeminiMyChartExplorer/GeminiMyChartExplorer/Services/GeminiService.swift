// Imports the fundamental Swift library for core functionalities.
import Foundation

/// An implementation of the `AdvisingService` protocol that uses the Google Gemini API to provide AI-driven insights.
struct GeminiService: AdvisingService {
    // Stores the API key required to authenticate with the Gemini API.
    private let apiKey: String
    // The base URL for the specific Gemini model being used.
    private let baseURL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

    /// Initializes the service with a specific API key.
    /// - Parameter apiKey: The key for accessing the Gemini API.
    init(apiKey: String) {
        self.apiKey = apiKey
    }

    // Helper structs to decode the expected JSON responses for specific requests.
    struct CategoriesResponse: Decodable { let categories: [String] }
    struct QueriesResponse: Decodable { let queries: [String] }
    
    /// A generic, reusable function to make an API request to the Gemini model and decode a JSON response.
    /// - Parameters:
    ///   - prompt: The text prompt to send to the AI model.
    ///   - jsonOutput: A boolean indicating whether to configure the API to return a JSON object.
    /// - Returns: A decoded object of the generic type `T`.
    /// - Throws: An error if the URL is invalid, the request fails, or the response cannot be parsed.
    private func makeAPIRequest<T: Decodable>(prompt: String, jsonOutput: Bool) async throws -> T {
        // Construct the full URL with the API key.
        guard let url = URL(string: "\(baseURL)?key=\(apiKey)") else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")

        // Create the request payload with the prompt.
        var payload: [String: Any] = ["contents": [["parts": [["text": prompt]]]]]
        // If JSON output is requested, add the necessary configuration to the payload.
        if jsonOutput { payload["generationConfig"] = ["responseMimeType": "application/json"] }
        
        // Serialize the payload into JSON data.
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        // Perform the asynchronous network request.
        let (data, response) = try await URLSession.shared.data(for: request)
        
        // Check for a successful HTTP response code.
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else { throw URLError(.badServerResponse) }
        
        // First, decode the outer Gemini API response structure.
        let initialResponse = try JSONDecoder().decode(GeminiAPIResponse.self, from: data)
        // Extract the actual text content, which contains the JSON string we need.
        guard let textContent = initialResponse.candidates.first?.content.parts.first?.text else { throw URLError(.cannotParseResponse) }
        
        // Convert the extracted text string into Data.
        let jsonData = Data(textContent.utf8)
        // Finally, decode that data into the expected generic type `T`.
        return try JSONDecoder().decode(T.self, from: jsonData)
    }
    
    /// A specialized function to make a plain text API request to the Gemini model.
    /// - Parameter prompt: The text prompt to send to the AI model.
    /// - Returns: A string containing the AI's text response.
    /// - Throws: An error if the URL is invalid, the request fails, or the response cannot be parsed.
    private func makeTextAPIRequest(prompt: String) async throws -> String {
        guard let url = URL(string: "\(baseURL)?key=\(apiKey)") else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")

        // Create the standard payload for a text request.
        let payload: [String: Any] = ["contents": [["parts": [["text": prompt]]]]]
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else { throw URLError(.badServerResponse) }
        
        // Decode the API response and directly extract the text content.
        let apiResponse = try JSONDecoder().decode(GeminiAPIResponse.self, from: data)
        return apiResponse.candidates.first?.content.parts.first?.text ?? "No response text found."
    }

    /// Asks the Gemini API to identify relevant medical data categories based on symptoms and a database schema.
    func getRelevantCategories(symptoms: String, schema: String) async throws -> [String] {
        let prompt = """
        A user is reporting the following symptoms: "\(symptoms)".
        Based on these symptoms, what categories of medical information would be most relevant to retrieve from their personal health record?
        The available tables and their schemas are:
        \(schema)
        
        Please respond with a JSON object containing a single key "categories" which is a list of strings. Each string should be a brief, user-friendly description of a relevant data category.
        For example: ["Recent blood pressure readings", "Current active medications", "History of surgeries related to the abdomen", "Recent clinical notes mentioning headaches"].
        """
        // Make the API call, expecting a `CategoriesResponse` object back.
        let response: CategoriesResponse = try await makeAPIRequest(prompt: prompt, jsonOutput: true)
        
        print("Retrieved categories: \(response.categories)")
        
        return response.categories
    }
    
    /// Asks the Gemini API to generate specific SQLite queries based on the identified categories and schema.
    func getSQLQueries(categories: [String], schema: String) async throws -> [String] {
        let prompt = """
        Based on the need for the following information categories: \(categories),
        and the following database schema:
        \(schema)
        
        Generate the SQLite3 queries required to retrieve this information.
        **IMPORTANT**: The queries must be very specific to retrieve only the minimal necessary data. Do NOT use `SELECT *`. Select only the specific columns needed. For any query on a table that has a `patient_id` column, you **MUST** include `WHERE patient_id = ?` in the query. For the `notes` table, use `WHERE note_content LIKE '%symptom%'` to find relevant notes. Use other `WHERE` clauses with dates or other conditions to further narrow down results where appropriate.
        
        Please respond with a JSON object containing a single key "queries" which is a list of strings, where each string is a single, valid SQLite3 query.
        Example of a good specific query: "SELECT medication_name, start_date FROM medications WHERE patient_id = ? AND status = 'active' ORDER BY start_date DESC LIMIT 5;"
        """
        // Make the API call, expecting a `QueriesResponse` object back.
        let response: QueriesResponse = try await makeAPIRequest(prompt: prompt, jsonOutput: true)
        
        print("Generated SQL queries: \(response.queries)")
        
        return response.queries
    }
    
    /// Asks the Gemini API to provide a final, structured analysis based on the user's symptoms and the retrieved medical data.
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
        // Make a plain text API call to get the final advice as a formatted string.
        return try await makeTextAPIRequest(prompt: prompt)
    }
    
    // MARK: - Per-Note Summarizer
    
    /// Asks the Gemini API to summarize a single clinical note, focusing on details relevant to the user's symptoms.
    func summarize(note: String, symptoms: String) async throws -> String {
        let prompt = """
        A user has the following symptoms: "\(symptoms)".
        Summarize the following clinical note concisely, focusing only on details relevant to these symptoms.

        NOTE:
        "\(note)"
        """
        // Use the plain text API helper to get the summary.
        return try await makeTextAPIRequest(prompt: prompt)
    }

    // MARK: - Reworked Processing Logic

    /// Processes the raw string of database results by summarizing clinical notes individually.
    func processDBResults(results: String, symptoms: String) async throws -> ProcessedDBResult {
        print("🤖 Processing DB results with per-note summarization (Gemini)...")
        
        // Split the raw result string into sections, one for each query that was run.
        let allQuerySections = results.components(separatedBy: "--- Query:")
                                      .filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        
        var fullContextBuilder = ""
        var notesForDisplayBuilder = ""

        // Process each query result section individually.
        for section in allQuerySections {
            let sectionTitle = "--- Query:" + section.lines.first!
            // Check if this section contains results from the 'notes' table.
            let isNotesSection = section.lowercased().contains("notes") && section.lowercased().contains("notecontent")

            if !isNotesSection {
                // If it's not a notes section, append the raw results to both the context and display strings.
                fullContextBuilder.append(sectionTitle + "\n" + section.lines.dropFirst().joined(separator: "\n") + "\n\n")
                notesForDisplayBuilder.append(sectionTitle + "\n" + section.lines.dropFirst().joined(separator: "\n") + "\n\n")
            } else {
                // If it IS a notes section, it requires special processing.
                print("Found notes section. Summarizing each note...")
                let lines = section.lines
                guard lines.count > 1 else { continue } // Skip if the section is empty.
                
                let header = lines[1] // The header line, e.g., "noteDate | noteTitle | noteContent"
                // Find the index of the 'noteContent' column to extract the note text.
                let contentColumnIndex = header.components(separatedBy: "|").firstIndex(where: { $0.trimmingCharacters(in: .whitespaces) == "noteContent" }) ?? -1

                // Add the header to both builders.
                fullContextBuilder.append(sectionTitle + "\n" + header + "\n")
                notesForDisplayBuilder.append(sectionTitle + "\n" + header + "\n")

                // Loop through each data row of the notes result.
                for rowString in lines.dropFirst(2) {
                    var columns = rowString.components(separatedBy: "|")
                    
                    // Check if the note content column was found and exists in this row.
                    if contentColumnIndex != -1 && columns.indices.contains(contentColumnIndex) {
                        let originalNote = columns[contentColumnIndex]
                        
                        // Call the `summarize` function for each individual note.
                        let summary = try await summarize(note: originalNote, symptoms: symptoms)
                        
                        // Replace the full note content with its summary in the column array.
                        columns[contentColumnIndex] = " [Summary] \(summary)"
                        
                        // Rebuild the row string with the summary.
                        let summarizedRow = columns.joined(separator: "|")
                        fullContextBuilder.append(summarizedRow + "\n")
                        notesForDisplayBuilder.append(summarizedRow + "\n")
                    } else {
                        // If there's no note content, just append the original row.
                        fullContextBuilder.append(rowString + "\n")
                    }
                }
                fullContextBuilder.append("\n")
                notesForDisplayBuilder.append("\n")
            }
        }
        
        print("✅ DB results processed.")

        // Return the final processed data in the required struct.
        return ProcessedDBResult(
            fullContext: fullContextBuilder,
            notesForDisplay: notesForDisplayBuilder.isEmpty ? "No relevant notes found." : notesForDisplayBuilder
        )
    }
}

// Helper structs specifically for decoding the nested JSON structure of the Gemini API response.
struct GeminiAPIResponse: Decodable { let candidates: [Candidate] }
struct Candidate: Decodable { let content: Content }
struct Content: Decodable { let parts: [Part] }
struct Part: Decodable { let text: String }
