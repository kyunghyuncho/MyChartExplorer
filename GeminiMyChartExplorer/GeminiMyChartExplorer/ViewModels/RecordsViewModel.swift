import Foundation
import Combine

@MainActor
class RecordsViewModel: ObservableObject {
    @Published var clinicalRecord: ClinicalRecord?
    @Published var searchText = ""
    @Published var isLoading = false
    
    // 1. Add this list for the navigation sidebar.
    let tableNames: [String] = [
        "Problems", "Medications", "Allergies", "Lab Results",
        "Procedures", "Immunizations", "Vitals", "Notes"
    ]
    
    private var dbManager: DatabaseManager?

    func setup(appState: AppState) {
        if let dbPath = appState.databasePath {
            self.dbManager = DatabaseManager(path: dbPath.path)
            fetchAllRecords()
        }
    }
    
    func fetchAllRecords() {
        guard let dbManager else { return }
        isLoading = true
        
        Task {
            self.clinicalRecord = try? await dbManager.fetchAllRecords()
            self.isLoading = false
        }
    }

    // MARK: - Filtered Data Properties

    private func filter<T>(_ records: [T], by keyPaths: [KeyPath<T, String?>]) -> [T] {
        if searchText.isEmpty {
            return records
        }
        let lowercasedSearchText = searchText.lowercased()
        return records.filter { record in
            keyPaths.contains { keyPath in
                record[keyPath: keyPath]?.lowercased().contains(lowercasedSearchText) ?? false
            }
        }
    }

    var filteredProblems: [Problem] {
        let problems = filter(clinicalRecord?.problems ?? [], by: [\.problemName, \.status])
        // 2. Filter out the specific "No known active problems" entry.
        return problems.filter { $0.problemName != "No known active problems" }
    }
    
    var filteredMedications: [Medication] {
        filter(clinicalRecord?.medications ?? [], by: [\.medicationName, \.instructions, \.status])
    }

    var filteredAllergies: [Allergy] {
        filter(clinicalRecord?.allergies ?? [], by: [\.substance, \.reaction, \.status])
    }

    var filteredLabResults: [LabResult] {
        filter(clinicalRecord?.results ?? [], by: [\.testName, \.value, \.interpretation])
    }

    var filteredProcedures: [Procedure] {
        filter(clinicalRecord?.procedures ?? [], by: [\.procedureName, \.provider])
    }

    var filteredImmunizations: [Immunization] {
        filter(clinicalRecord?.immunizations ?? [], by: [\.vaccineName])
    }
    
    var filteredVitals: [Vital] {
        filter(clinicalRecord?.vitals ?? [], by: [\.vitalSign, \.value])
    }
    
    var filteredNotes: [Note] {
        filter(clinicalRecord?.notes ?? [], by: [\.noteTitle, \.noteContent, \.provider, \.noteType])
    }
}
