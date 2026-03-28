// Imports the fundamental Swift library, which provides core functionalities.
import Foundation

/// A protocol that defines a standard interface for any service designed to provide AI-driven medical advice.
/// It outlines the necessary functions for processing symptoms, interacting with a database,
/// and generating final recommendations or summaries.
protocol AdvisingService {
    
    /// Asynchronously determines the most relevant medical data categories (e.g., allergies, medications, lab results)
    /// based on a user's reported symptoms and the structure of the medical database.
    /// - Parameters:
    ///   - symptoms: A string describing the user's symptoms.
    ///   - schema: A string detailing the database schema, including tables and columns.
    /// - Returns: An array of strings, where each string is a relevant category name (like a table name).
    /// - Throws: An error if the categories cannot be determined (e.g., network issue, API error).
    func getRelevantCategories(symptoms: String, schema: String) async throws -> [String]
    
    /// Asynchronously generates SQL queries to retrieve data from the categories identified as relevant.
    /// - Parameters:
    ///   - categories: An array of data categories (table names) to query.
    ///   - schema: A string detailing the database schema to help in constructing valid queries.
    /// - Returns: An array of strings, where each string is a complete SQL query.
    /// - Throws: An error if the SQL queries cannot be generated.
    func getSQLQueries(categories: [String], schema: String) async throws -> [String]
    
    /// Asynchronously generates a final, human-readable analysis or piece of advice.
    /// This is based on the initial symptoms and the contextual data retrieved from the database.
    /// - Parameters:
    ///   - symptoms: The original string of user-reported symptoms.
    ///   - context: A string containing all the relevant medical data retrieved from the database.
    /// - Returns: A string containing the final advice or analysis.
    /// - Throws: An error if the final advice cannot be generated.
    func getFinalAdvice(symptoms: String, context: String) async throws -> String
    
    /// Asynchronously creates a concise summary of a single clinical note, focusing on information
    /// relevant to the user's reported symptoms.
    /// - Parameters:
    ///   - note: The full text of the clinical note to be summarized.
    ///   - symptoms: The user's symptoms, providing context for the summarization.
    /// - Returns: A string containing the summarized version of the note.
    /// - Throws: An error if the note cannot be summarized.
    func summarize(note: String, symptoms: String) async throws -> String
    
    /// Asynchronously processes a raw string of database results. It separates out clinical notes,
    /// summarizes them, and then combines them back into a full context for further AI analysis.
    /// - Parameters:
    ///   - results: A string containing the raw data fetched from the database.
    ///   - symptoms: The user's symptoms, which provide context for summarizing any notes found in the results.
    /// - Returns: A `ProcessedDBResult` struct containing both the full context for the AI and a display-friendly string of summarized notes.
    /// - Throws: An error if the results cannot be processed.
    func processDBResults(results: String, symptoms: String) async throws -> ProcessedDBResult
}

/// A structure designed to hold the structured output from the `processDBResults` function.
/// It separates the complete data needed for the AI from the summarized notes intended for user display.
struct ProcessedDBResult {
    /// A comprehensive string that includes all retrieved database information,
    /// with any clinical notes replaced by their summaries. This is optimized for the final AI analysis call.
    let fullContext: String
    
    /// A string that contains only the summarized notes, formatted for clear presentation in the user interface.
    let notesForDisplay: String
}

// An extension to the built-in String class to add convenient functionality.
extension String {
    /// A computed property that splits a multi-line string into an array of individual lines.
    /// It uses the newline character as the delimiter.
    var lines: [String] {
        self.components(separatedBy: .newlines)
    }
}
