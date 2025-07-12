import Foundation
import SwiftUI

@MainActor
class DataImporter: ObservableObject {
    @Published var isImporting: Bool = false
    @Published var xmlFiles: [URL] = []
    @Published var databaseURL: URL?
    @Published var logOutput: String = ""
    @Published var canStartImport: Bool = false
    
    private var dbManager: DatabaseManager?

    func selectFiles() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true
        panel.canChooseDirectories = false
        panel.allowsMultipleSelection = true
        panel.allowedContentTypes = [.xml]
        if panel.runModal() == .OK {
            self.xmlFiles.append(contentsOf: panel.urls)
            updateCanStart()
        }
    }
    
    func clearFiles() {
        self.xmlFiles.removeAll()
        updateCanStart()
    }
    
    func setDatabaseDestination() {
        let panel = NSSavePanel()
        panel.allowedFileTypes = ["db"]
        panel.nameFieldStringValue = "MyHealthData.db"
        if panel.runModal() == .OK {
            self.databaseURL = panel.url
            updateCanStart()
        }
    }
    
    private func updateCanStart() {
        canStartImport = !xmlFiles.isEmpty && databaseURL != nil
    }
    
    func clearLog() {
        logOutput = ""
    }
    
    func startImport(completion: @escaping (URL?) -> Void) {
        guard let dbURL = databaseURL else {
            log("Error: Database destination not set.")
            completion(nil)
            return
        }

        log("--- Starting Import Process ---")
        dbManager = DatabaseManager(path: dbURL.path)
        
        // 1. Tell the UI we are starting.
        self.isImporting = true

        Task {
            do {
                try dbManager?.createTables()
                log("Database schema verified.")

                // Process files one by one, waiting for each to complete.
                for fileURL in xmlFiles {
                    do {
                        log("Processing: \(fileURL.lastPathComponent)")
                        let parsedRecords: ParsedRecords = try await withCheckedThrowingContinuation { continuation in
                            let parser = XMLFileParser()
                            parser.parse(from: fileURL) { result in
                                switch result {
                                case .success(let records):
                                    continuation.resume(returning: records)
                                case .failure(let error):
                                    self.log("🛑 Error parsing \(fileURL.lastPathComponent): \(error.localizedDescription)")
                                    continuation.resume(throwing: error)
                                }
                            }
                        }
                        let newRecordCount = try await dbManager?.insertData(parsedRecords)
                        log("✅ Inserted \(newRecordCount ?? 0) new records from \(fileURL.lastPathComponent)")
                    } catch {
                        // Skip this file and continue with the next
                        log("🛑 Skipping \(fileURL.lastPathComponent) due to error: \(error.localizedDescription)")
                        continue
                    }
                }
                
                // This now correctly runs only after all files are processed.
                log("--- Import Complete! ---")
                completion(dbURL)

            } catch {
                // Any error from parsing or inserting will be caught here.
                log("🛑 Error during import: \(error.localizedDescription)")
                completion(nil)
            }
            
            // 2. Tell the UI we are finished, whether it succeeded or failed.
            self.isImporting = false
        }
    }
    
    private func log(_ message: String) {
        let timestamp = Date().formatted(date: .omitted, time: .standard)
        logOutput += "[\(timestamp)] \(message)\n"
    }
}
