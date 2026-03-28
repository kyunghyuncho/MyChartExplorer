// Imports the fundamental Swift library for core functionalities.
import Foundation

// NOTE: These response structs are for decoding the JSON content *within* the AI's response.
// They are identical to the ones used by other services and can be defined in a shared location.
struct CategoriesResponse: Decodable { let categories: [String] }
struct QueriesResponse: Decodable { let queries: [String] }
struct CorrectedQueryResponse: Decodable { let query: String }


/// An implementation of the `AdvisingService` protocol that uses a local Ollama instance to provide AI-driven insights.
/// This allows for using open-source models running on the user's machine or local network.
struct OllamaService : AdvisingService {
    // The name of the Ollama model to use (e.g., "llama3", "mistral").
    private let model: String
    // The base URL of the Ollama server (e.g., "http://localhost:11434").
    private let host: String
    // The full URL for the '/api/generate' endpoint.
    private let apiURL: URL
    // Use its own URLSession instance to avoid conflicts with other network requests.
    private let urlSession: URLSession
    
    /// Initializes the service.
    /// - Parameters:
    ///   - model: The name of the Ollama model to use. Defaults to "gemma3:1b-it-qat".
    ///   - host: The host address of the Ollama server. Defaults to "http://localhost:11434".
    init(model: String = "gemma3:1b-it-qat",
         host: String = "http://localhost:11434") {
        self.model = model
        self.host = host
        // The URL is constructed from the host string. We can safely force-unwrap here
        // because the default and expected host strings are known to be valid URL formats.
        self.apiURL = URL(string: "\(host)/api/generate")!

        // Configure and create the custom URLSession instance
        let configuration = URLSessionConfiguration.default
        // Set the timeout to 6 minutes (360 seconds). Adjust as needed.
        configuration.timeoutIntervalForRequest = 360.0
        configuration.timeoutIntervalForResource = 360.0
        self.urlSession = URLSession(configuration: configuration)
    }

    // MARK: - Private API Request Handlers

    /// A generic helper function for making API requests to Ollama that expect a JSON object in the response.
    /// - Parameter prompt: The text prompt to send to the model.
    /// - Returns: A decoded object of the generic type `T`.
    /// - Throws: An error if the request fails or the response cannot be parsed.
    private func makeAPIRequest<T: Decodable>(prompt: String) async throws -> T {
        var request = URLRequest(url: apiURL)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")

        // Create the payload for the Ollama API, specifying "json" as the format to ensure the model returns a valid JSON string.
        let payload = OllamaRequestPayload(model: self.model, prompt: prompt, format: "json")
        request.httpBody = try JSONEncoder().encode(payload)
        
        let (data, response) = try await urlSession.data(for: request)

        // Ensure the HTTP response is successful.
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
        
        // First, decode the main Ollama response wrapper.
        let ollamaResponse = try JSONDecoder().decode(OllamaAPIResponse.self, from: data)
        
        // The actual content we need is a string inside the 'response' key. Convert this string to Data.
        guard let responseStringData = ollamaResponse.response.data(using: .utf8) else {
            throw URLError(.cannotParseResponse)
        }
        
        // Now, decode the nested JSON string (which is now Data) into the target generic type <T>.
        return try JSONDecoder().decode(T.self, from: responseStringData)
    }

    /// A helper function for making API requests that expect a plain text string in the response.
    /// - Parameter prompt: The text prompt to send to the model.
    /// - Returns: A string containing the model's plain text response.
    /// - Throws: An error if the request fails.
    private func makeTextAPIRequest(prompt: String) async throws -> String {
        var request = URLRequest(url: apiURL)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")

        // Create the payload for a plain text response (the 'format' property is omitted).
        let payload = OllamaRequestPayload(model: self.model, prompt: prompt)
        request.httpBody = try JSONEncoder().encode(payload)

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }

        // Decode the Ollama response and return the 'response' string directly.
        let ollamaResponse = try JSONDecoder().decode(OllamaAPIResponse.self, from: data)
        return ollamaResponse.response
    }
    
    // MARK: - Public Service Methods

    /// Asks the Ollama model to identify relevant medical data categories based on symptoms and a database schema.
    func getRelevantCategories(symptoms: String, schema: String) async throws -> [String] {
        let prompt = """
        A user is reporting the following symptoms: "\(symptoms)".
        Based on these symptoms, what categories of medical information would be most relevant to retrieve from their personal health record?
        The available tables and their schemas are:
        \(schema)
        
        Please respond with a JSON object containing a single key "categories" which is a list of table names from the database schema above.
        """
        // The generic type <CategoriesResponse> is inferred by the compiler from the function's return type signature.
        let response: CategoriesResponse = try await makeAPIRequest(prompt: prompt)
        
        print("Retrieved categories (Ollama): \(response.categories)")
        
        return response.categories
    }
    
    /// Asks the Ollama model to generate specific SQLite queries based on the identified categories and schema.
    func getSQLQueries(categories: [String], schema: String) async throws -> [String] {
        let prompt = """
        Based on the need for the following information categories: \(categories),
        and the following database schema:
        \(schema)
        
        **IMPORTANT**: Strictly stick to the schema provided. Do not assume any additional columns or tables. Your and my lives depend on it.
        
        Generate the SQLite3 queries required to retrieve this information.
        **IMPORTANT**: The queries must be very specific to retrieve only the minimal but sufficient data. Avoid using `SELECT *` too often. Select only the specific columns needed. For any query on a table that has a `patientId` column, you **MUST** include `WHERE patientId = ?` in the query. For the `notes` table, use `WHERE noteContent LIKE '%symptom%'` to find relevant notes. Use other `WHERE` clauses with dates or other conditions to further narrow down results where appropriate. Use `LIMIT` clauses to restrict the number of results to a reasonable amount (e.g., 5-10 recent entries). 
        
        **IMPORTANT**: Our lives depend on how short, succinct and specific retrieved data is. 
        
        Please respond with a JSON object containing a single key "queries" which is a list of strings, where each string is a single, valid SQLite3 query.
        Example of good specific queries: "SELECT medicationName, startDate FROM medications WHERE patientId = ? AND status = 'active' ORDER BY startDate DESC LIMIT 5;"
        Do NOT simply copy this example as is. It will not work for our specific database schema and needs.
        It is very likely you must create multiple queries to cover all relevant categories.
        """
        let response: QueriesResponse = try await makeAPIRequest(prompt: prompt)
        
        print("Generated SQL queries (Ollama): \(response.queries)")
        
        return response.queries
    }
    
    /// Asks the Ollama model to correct a failed SQL query based on the error message.
    func getCorrectedSQLQuery(failedQuery: String, errorMessage: String, schema: String) async throws -> String {
        print("Attempting to correct failed SQL query...")
        let prompt = """
        The following SQLite3 query failed to execute:
        `\(failedQuery)`

        It produced this error:
        `\(errorMessage)`

        Here is the database schema again for reference:
        \(schema)

        Please correct the query. Respond with a JSON object containing a single key "query" with the corrected, valid SQLite3 query string. It must run correctly this time in order to ensure we serve the patient better!
        """
        let response: CorrectedQueryResponse = try await makeAPIRequest(prompt: prompt)
        print("Received corrected query: \(response.query)")
        return response.query
    }

    /// Asks the Ollama model to provide a final, structured analysis based on the user's symptoms and retrieved medical data.
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
    
    // MARK: - Per-Note Summarizer
    
    /// Asks the Ollama model to summarize a single clinical note, focusing on details relevant to the user's symptoms.
    func summarize(note: String, symptoms: String) async throws -> String {
        let prompt = """
        A user has the following symptoms: "\(symptoms)".
        Summarize the following clinical note concisely, focusing only on details relevant to these symptoms.
        It is extremely important to keep the summary short and focused on the most relevant information.
        Keep the summary to a few sentences at most, ideally one or two.
        Everyone's life depends on how short, succinct and specific the summary is.

        NOTE:
        "\(note)"
        """
        // This uses the helper for plain text API calls to get the summary.
        return try await makeTextAPIRequest(prompt: prompt)
    }

    // MARK: - Reworked Processing Logic

    /// Processes the raw string of database results by summarizing clinical notes and squashing duplicates in other data.
    func processDBResults(results: String, symptoms: String) async throws -> ProcessedDBResult {
        print("🤖 Processing DB results with per-note summarization and duplicate squashing (Ollama)...")
        
        let allQuerySections = results.components(separatedBy: "--- Query:")
                                      .filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        
        var fullContextBuilder = ""
        var notesForDisplayBuilder = ""

        for section in allQuerySections {
            let sectionTitle = "--- Query:" + section.lines.first!
            let isNotesSection = section.lowercased().contains("notes") && section.lowercased().contains("notecontent")

            if !isNotesSection {
                let squashedResult = squashDuplicateRows(in: section)
                fullContextBuilder.append(sectionTitle + "\n" + squashedResult + "\n\n")
            } else {
                print("Found notes section. Summarizing each note...")
                let lines = section.lines
                guard lines.count > 1 else { continue }
                
                let header = lines[1]
                let contentColumnIndex = header.components(separatedBy: "|").firstIndex { $0.trimmingCharacters(in: .whitespaces) == "noteContent" } ?? -1

                fullContextBuilder.append(sectionTitle + "\n" + header + "\n")
                notesForDisplayBuilder.append(sectionTitle + "\n" + header + "\n")

                for rowString in lines.dropFirst(2) {
                    var columns = rowString.components(separatedBy: "|")
                    
                    if contentColumnIndex != -1 && columns.indices.contains(contentColumnIndex) {
                        let originalNote = columns[contentColumnIndex]
                        let summary = try await summarize(note: originalNote, symptoms: symptoms)
                        columns[contentColumnIndex] = " [Summary] \(summary)"
                        
                        let summarizedRow = columns.joined(separator: "|")
                        fullContextBuilder.append(summarizedRow + "\n")
                        notesForDisplayBuilder.append(summarizedRow + "\n")
                    } else {
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
    
    /// A helper function to identify and consolidate duplicate rows within a single query result section.
    /// - Parameter section: The string content of a single query result.
    /// - Returns: A string with duplicate rows consolidated and counted.
    private func squashDuplicateRows(in section: String) -> String {
        let lines = section.lines.dropFirst().filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }
        guard let header = lines.first else { return "" }

        let dataRows = lines.dropFirst()

        var rowCounts: [String: Int] = [:]
        var orderedRows: [String] = []

        for row in dataRows {
            let trimmedRow = row.trimmingCharacters(in: .whitespaces)
            if rowCounts[trimmedRow] == nil {
                orderedRows.append(trimmedRow)
            }
            rowCounts[trimmedRow, default: 0] += 1
        }

        let squashedRows = orderedRows.map { row -> String in
            let count = rowCounts[row]!
            return count > 1 ? "\(row) (x\(count))" : row
        }

        return ([header] + squashedRows).joined(separator: "\n")
    }
}

// MARK: - Helper Structs for Ollama API

/// Represents the JSON payload to be sent in the body of a request to the Ollama API.
private struct OllamaRequestPayload: Codable {
    let model: String
    let prompt: String
    let stream: Bool = false // We want the full response at once, not a streaming response.
    var format: String? = nil // Can be set to "json" to enforce JSON output from the model.
}

/// Represents the top-level JSON response from the Ollama API.
private struct OllamaAPIResponse: Decodable {
    /// The actual text or JSON string generated by the model.
    let response: String
    let model: String
    let createdAt: String
    let done: Bool

    // Maps the 'created_at' key from the JSON to the Swift-standard 'createdAt' camelCase property.
    enum CodingKeys: String, CodingKey {
        case response, model, done
        case createdAt = "created_at"
    }
}
