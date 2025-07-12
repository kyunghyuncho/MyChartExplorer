import Foundation

struct GeminiService {
    private let apiKey: String
    private let baseURL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

    init(apiKey: String) {
        self.apiKey = apiKey
    }

    struct CategoriesResponse: Decodable { let categories: [String] }
    struct QueriesResponse: Decodable { let queries: [String] }
    
    private func makeAPIRequest<T: Decodable>(prompt: String, jsonOutput: Bool) async throws -> T {
        guard let url = URL(string: "\(baseURL)?key=\(apiKey)") else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")

        var payload: [String: Any] = ["contents": [["parts": [["text": prompt]]]]]
        if jsonOutput { payload["generationConfig"] = ["responseMimeType": "application/json"] }
        
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        let (data, response) = try await URLSession.shared.data(for: request)
        
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else { throw URLError(.badServerResponse) }
        
        let initialResponse = try JSONDecoder().decode(GeminiAPIResponse.self, from: data)
        guard let textContent = initialResponse.candidates.first?.content.parts.first?.text else { throw URLError(.cannotParseResponse) }
        
        let jsonData = Data(textContent.utf8)
        return try JSONDecoder().decode(T.self, from: jsonData)
    }
    
    private func makeTextAPIRequest(prompt: String) async throws -> String {
        guard let url = URL(string: "\(baseURL)?key=\(apiKey)") else { throw URLError(.badURL) }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")

        let payload: [String: Any] = ["contents": [["parts": [["text": prompt]]]]]
        request.httpBody = try JSONSerialization.data(withJSONObject: payload)
        
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else { throw URLError(.badServerResponse) }
        
        let apiResponse = try JSONDecoder().decode(GeminiAPIResponse.self, from: data)
        return apiResponse.candidates.first?.content.parts.first?.text ?? "No response text found."
    }

    // **FIXED**: Prompts updated to match the successful Python implementation.
    func getRelevantCategories(symptoms: String, schema: String) async throws -> [String] {
        let prompt = """
        A user is reporting the following symptoms: "\(symptoms)".
        Based on these symptoms, what categories of medical information would be most relevant to retrieve from their personal health record?
        The available tables and their schemas are:
        \(schema)
        
        Please respond with a JSON object containing a single key "categories" which is a list of strings. Each string should be a brief, user-friendly description of a relevant data category.
        For example: ["Recent blood pressure readings", "Current active medications", "History of surgeries related to the abdomen", "Recent clinical notes mentioning headaches"].
        """
        let response: CategoriesResponse = try await makeAPIRequest(prompt: prompt, jsonOutput: true)
        
        print("Retrieved categories: \(response.categories)")
        
        return response.categories
    }
    
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
        let response: QueriesResponse = try await makeAPIRequest(prompt: prompt, jsonOutput: true)
        
        print("Generated SQL queries: \(response.queries)")
        
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
}

// Helper structs for decoding the Gemini API's wrapper JSON
struct GeminiAPIResponse: Decodable { let candidates: [Candidate] }
struct Candidate: Decodable { let content: Content }
struct Content: Decodable { let parts: [Part] }
struct Part: Decodable { let text: String }
