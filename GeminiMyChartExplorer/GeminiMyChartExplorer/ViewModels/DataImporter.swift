// Imports the fundamental Swift library for core functionalities.
import Foundation
// Imports the SwiftUI framework for UI components and state management.
import SwiftUI

/// A view model responsible for managing the data import process.
/// It handles file selection, database destination, and orchestrates the parsing and insertion of data.
/// It is marked with `@MainActor` to ensure all UI updates happen on the main thread.
@MainActor
class DataImporter: ObservableObject {
    // MARK: - Published Properties for UI State
    
    /// A boolean flag to indicate when the import process is active, used for showing loading indicators.
    @Published var isImporting: Bool = false
    /// An array of URLs pointing to the selected XML files to be imported.
    @Published var xmlFiles: [URL] = []
    /// The URL for the destination SQLite database file.
    @Published var databaseURL: URL?
    /// A string that accumulates log messages to display the import progress and any errors in the UI.
    @Published var logOutput: String = ""
    /// A boolean flag that controls whether the "Start Import" button is enabled in the UI.
    @Published var canStartImport: Bool = false
    
    /// The manager for handling all database interactions. It's optional because it's only created when an import starts.
    private var dbManager: DatabaseManager?

    /// Opens a system panel allowing the user to select one or more XML files.
    func selectFiles() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = true
        panel.allowedContentTypes = [.xml] // Restrict selection to XML files.
        
        // If the user clicks "OK", append the selected file URLs to our list.
        if panel.runModal() == .OK {
            self.xmlFiles.append(contentsOf: panel.urls)
            updateCanStart() // Check if the import can now be started.
        }
    }
    
    /// Clears the list of selected XML files.
    func clearFiles() {
        self.xmlFiles.removeAll()
        updateCanStart()
    }
    
    /// Opens a system panel allowing the user to choose a location and name for the new database file.
    func setDatabaseDestination() {
        let panel = NSSavePanel()
        panel.allowedFileTypes = ["db"]
        panel.nameFieldStringValue = "MyHealthData.db" // Suggest a default file name.
        
        // If the user confirms a location, store the destination URL.
        if panel.runModal() == .OK {
            self.databaseURL = panel.url
            updateCanStart()
        }
    }
    
    /// Updates the `canStartImport` flag based on whether both files and a destination have been selected.
    private func updateCanStart() {
        canStartImport = !xmlFiles.isEmpty && databaseURL != nil
    }
    
    /// Clears the log output string.
    func clearLog() {
        logOutput = ""
    }
    
    /// Begins the asynchronous import process.
    /// - Parameter completion: A closure that is called when the import is finished, passing the URL of the created database or nil on failure.
    func startImport(completion: @escaping (URL?) -> Void) {
        guard let dbURL = databaseURL else {
            log("Error: Database destination not set.")
            completion(nil)
            return
        }

        log("--- Starting Import Process ---")
        // Initialize the database manager with the chosen path.
        dbManager = DatabaseManager(path: dbURL.path)
        
        // 1. Update the UI to show that the import is in progress.
        self.isImporting = true

        // Run the entire import process within a background Task.
        Task {
            do {
                // Ensure the database tables are created.
                try dbManager?.createTables()
                log("Database schema verified.")

                // Process each selected file sequentially.
                for fileURL in xmlFiles {
                    do {
                        log("Processing: \(fileURL.lastPathComponent)")
                        // Bridge the callback-based XML parser with async/await using a continuation.
                        let parsedRecords: ParsedRecords = try await withCheckedThrowingContinuation { continuation in
                            let parser = XMLFileParser()
                            parser.parse(from: fileURL) { result in
                                switch result {
                                case .success(let records):
                                    // If parsing succeeds, resume the Task with the returned records.
                                    continuation.resume(returning: records)
                                case .failure(let error):
                                    // If parsing fails, log the error and resume the Task by throwing the error.
                                    self.log("🛑 Error parsing \(fileURL.lastPathComponent): \(error.localizedDescription)")
                                    continuation.resume(throwing: error)
                                }
                            }
                        }
                        // Insert the newly parsed data into the database.
                        let newRecordCount = try await dbManager?.insertData(parsedRecords)
                        log("✅ Inserted \(newRecordCount ?? 0) new records from \(fileURL.lastPathComponent)")
                    } catch {
                        // If an error occurs for a single file (parsing or insertion), log it and continue to the next file.
                        log("🛑 Skipping \(fileURL.lastPathComponent) due to error: \(error.localizedDescription)")
                        continue
                    }
                }
                
                // This code runs only after the loop has successfully completed for all files.
                log("--- Import Complete! ---")
                completion(dbURL)

            } catch {
                // This catches any errors from the initial `createTables` call.
                log("🛑 Error during import: \(error.localizedDescription)")
                completion(nil)
            }
            
            // 2. Update the UI to show that the import has finished.
            self.isImporting = false
        }
    }
    
    /// Appends a message to the log string with a timestamp.
    /// - Parameter message: The string to be logged.
    private func log(_ message: String) {
        let timestamp = Date().formatted(date: .omitted, time: .standard)
        logOutput += "[\(timestamp)] \(message)\n"
    }
}
