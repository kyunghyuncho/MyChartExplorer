import Foundation

/// A protocol defining the common capabilities for any AI advising service.
protocol AdvisingService {
    /// Determines relevant data categories based on symptoms and a database schema.
    func getRelevantCategories(symptoms: String, schema: String) async throws -> [String]
    
    /// Generates SQL queries based on data categories and a database schema.
    func getSQLQueries(categories: [String], schema: String) async throws -> [String]
    
    /// Provides a final analysis based on symptoms and retrieved medical context.
    func getFinalAdvice(symptoms: String, context: String) async throws -> String
    
    /// Summarizes a single clinical note in the context of user symptoms.
    func summarize(note: String, symptoms: String) async throws -> String
    
   // This function is now updated to return the new struct
    func processDBResults(results: String, symptoms: String) async throws -> ProcessedDBResult
}

/// A structure to hold the processed results from the database.
struct ProcessedDBResult {
    /// The complete context, with notes summarized, for the final AI call.
    let fullContext: String
    
    /// A string containing only the summarized notes, intended for UI display.
    let notesForDisplay: String
}

// Helper extension to make string parsing easier
extension String {
    var lines: [String] {
        self.components(separatedBy: .newlines)
    }
}
