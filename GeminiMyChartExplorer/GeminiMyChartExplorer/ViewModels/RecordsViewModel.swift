// Imports the fundamental Swift library for core functionalities.
import Foundation
// Imports the Combine framework for declarative Swift APIs for processing values over time.
import Combine

/// The view model for the "Browse Records" screen.
/// It is responsible for fetching the complete clinical record from the database,
/// holding the state for the UI, and providing computed properties for filtering the data based on user search input.
/// It is marked with `@MainActor` to ensure all UI updates happen on the main thread.
@MainActor
class RecordsViewModel: ObservableObject {
    // MARK: - Published Properties for UI State
    
    /// Holds the complete, structured clinical record for the patient.
    /// It is optional because it might not be loaded initially.
    @Published var clinicalRecord: ClinicalRecord?
    /// The current text entered by the user in the search bar.
    @Published var searchText = ""
    /// A boolean flag to indicate when data is being fetched from the database, used for showing loading indicators.
    @Published var isLoading = false
    
    /// A static list of medical record categories, used to populate the navigation sidebar in the UI.
    let tableNames: [String] = [
        "Problems", "Medications", "Allergies", "Lab Results",
        "Procedures", "Immunizations", "Vitals", "Notes"
    ]
    
    /// The manager for handling all database interactions.
    private var dbManager: DatabaseManager?

    /// Sets up the view model with the necessary database manager from the global app state.
    /// - Parameter appState: The shared application state containing the database path.
    func setup(appState: AppState) {
        if let dbPath = appState.databasePath {
            self.dbManager = DatabaseManager(path: dbPath.path)
            // Once the database manager is set up, immediately fetch all records.
            fetchAllRecords()
        }
    }
    
    /// Fetches the entire clinical record from the database asynchronously.
    func fetchAllRecords() {
        guard let dbManager else { return }
        isLoading = true
        
        // Run the database fetch operation in a background Task.
        Task {
            // The result of the fetch operation is assigned to the `clinicalRecord` property.
            // Any errors are suppressed with `try?`, resulting in `nil` if the fetch fails.
            self.clinicalRecord = try? await dbManager.fetchAllRecords()
            // Once the operation is complete, set isLoading back to false.
            self.isLoading = false
        }
    }

    // MARK: - Filtered Data Properties

    /// A generic, reusable function to filter an array of records based on the `searchText`.
    /// - Parameters:
    ///   - records: The array of records to filter.
    ///   - keyPaths: An array of key paths to the string properties that should be searched within each record.
    /// - Returns: A new array containing only the records that match the search text.
    private func filter<T>(_ records: [T], by keyPaths: [KeyPath<T, String?>]) -> [T] {
        // If the search text is empty, return the original, unfiltered array.
        if searchText.isEmpty {
            return records
        }
        let lowercasedSearchText = searchText.lowercased()
        // Filter the records array.
        return records.filter { record in
            // A record is included if any of its specified key paths contain the search text.
            keyPaths.contains { keyPath in
                record[keyPath: keyPath]?.lowercased().contains(lowercasedSearchText) ?? false
            }
        }
    }

    /// A computed property that returns a filtered list of health problems.
    var filteredProblems: [Problem] {
        let problems = filter(clinicalRecord?.problems ?? [], by: [\.problemName, \.status])
        // Also, explicitly filter out any entry that is just a placeholder for "No known active problems".
        return problems.filter { $0.problemName != "No known active problems" }
    }
    
    /// A computed property that returns a filtered list of medications.
    var filteredMedications: [Medication] {
        filter(clinicalRecord?.medications ?? [], by: [\.medicationName, \.instructions, \.status])
    }

    /// A computed property that returns a filtered list of allergies.
    var filteredAllergies: [Allergy] {
        filter(clinicalRecord?.allergies ?? [], by: [\.substance, \.reaction, \.status])
    }

    /// A computed property that returns a filtered list of lab results.
    var filteredLabResults: [LabResult] {
        filter(clinicalRecord?.results ?? [], by: [\.testName, \.value, \.interpretation])
    }

    /// A computed property that returns a filtered list of procedures.
    var filteredProcedures: [Procedure] {
        filter(clinicalRecord?.procedures ?? [], by: [\.procedureName, \.provider])
    }

    /// A computed property that returns a filtered list of immunizations.
    var filteredImmunizations: [Immunization] {
        filter(clinicalRecord?.immunizations ?? [], by: [\.vaccineName])
    }
    
    /// A computed property that returns a filtered list of vital signs.
    var filteredVitals: [Vital] {
        filter(clinicalRecord?.vitals ?? [], by: [\.vitalSign, \.value])
    }
    
    /// A computed property that returns a filtered list of clinical notes.
    var filteredNotes: [Note] {
        filter(clinicalRecord?.notes ?? [], by: [\.noteTitle, \.noteContent, \.provider, \.noteType])
    }
}
