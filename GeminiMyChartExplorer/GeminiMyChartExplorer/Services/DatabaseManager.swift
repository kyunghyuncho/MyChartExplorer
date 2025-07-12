// DatabaseManager.swift

import Foundation
import GRDB

class DatabaseManager {
    let dbQueue: DatabaseQueue

    init(path: String) {
        do {
            dbQueue = try DatabaseQueue(path: path)
            try createTables()
        } catch {
            fatalError("Could not connect to or set up database: \(error)")
        }
    }
    
    /// Creates all necessary tables with unique constraints to prevent duplication.
    public func createTables() throws {
        try dbQueue.write { db in
            try db.create(table: Patient.databaseTableName, ifNotExists: true) { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("mrn", .text)
                t.column("givenName", .text)
                t.column("familyName", .text)
                t.column("dob", .text)
                t.column("gender", .text)
                t.column("maritalStatus", .text)
                t.column("race", .text)
                t.column("ethnicity", .text)
                t.column("deceased", .boolean)
                t.column("deceasedDate", .text)
                t.uniqueKey(["mrn", "givenName", "familyName", "dob"])
            }
            
            try db.create(table: Allergy.databaseTableName, ifNotExists: true) { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("patientId", .integer).notNull().references(Patient.databaseTableName, onDelete: .cascade)
                t.column("substance", .text)
                t.column("reaction", .text)
                t.column("status", .text)
                t.column("effectiveDate", .text)
                t.uniqueKey(["patientId", "substance", "effectiveDate"])
            }
            
            try db.create(table: Problem.databaseTableName, ifNotExists: true) { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("patientId", .integer).notNull().references(Patient.databaseTableName, onDelete: .cascade)
                t.column("problemName", .text)
                t.column("status", .text)
                t.column("onsetDate", .text)
                t.column("resolvedDate", .text)
                t.uniqueKey(["patientId", "problemName", "onsetDate"])
            }
            
            try db.create(table: Medication.databaseTableName, ifNotExists: true) { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("patientId", .integer).notNull().references(Patient.databaseTableName, onDelete: .cascade)
                t.column("medicationName", .text)
                t.column("instructions", .text)
                t.column("status", .text)
                t.column("startDate", .text)
                t.column("endDate", .text)
                t.uniqueKey(["patientId", "medicationName", "startDate"])
            }
            
            try db.create(table: Immunization.databaseTableName, ifNotExists: true) { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("patientId", .integer).notNull().references(Patient.databaseTableName, onDelete: .cascade)
                t.column("vaccineName", .text)
                t.column("dateAdministered", .text)
                t.uniqueKey(["patientId", "vaccineName", "dateAdministered"])
            }
            
            try db.create(table: Vital.databaseTableName, ifNotExists: true) { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("patientId", .integer).notNull().references(Patient.databaseTableName, onDelete: .cascade)
                t.column("vitalSign", .text)
                t.column("value", .text)
                t.column("unit", .text)
                t.column("effectiveDate", .text)
                t.uniqueKey(["patientId", "vitalSign", "effectiveDate"])
            }
            
            try db.create(table: LabResult.databaseTableName, ifNotExists: true) { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("patientId", .integer).notNull().references(Patient.databaseTableName, onDelete: .cascade)
                t.column("testName", .text)
                t.column("value", .text)
                t.column("unit", .text)
                t.column("referenceRange", .text)
                t.column("interpretation", .text)
                t.column("effectiveDate", .text)
                t.uniqueKey(["patientId", "testName", "effectiveDate"])
            }
            
            try db.create(table: Procedure.databaseTableName, ifNotExists: true) { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("patientId", .integer).notNull().references(Patient.databaseTableName, onDelete: .cascade)
                t.column("procedureName", .text)
                t.column("date", .text)
                t.column("provider", .text)
                t.uniqueKey(["patientId", "procedureName", "date"])
            }
            
            try db.create(table: Note.databaseTableName, ifNotExists: true) { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("patientId", .integer).notNull().references(Patient.databaseTableName, onDelete: .cascade)
                t.column("noteType", .text)
                t.column("noteDate", .text)
                t.column("noteTitle", .text)
                t.column("noteContent", .text)
                t.column("provider", .text)
                t.uniqueKey(["patientId", "noteDate", "noteTitle"])
            }
        }
    }

    /// Inserts parsed records into the database, ignoring any duplicates.
    /// - Parameter records: The `ParsedRecords` object from the XML parser.
    /// - Returns: The total number of new rows inserted across all tables.
    func insertData(_ records: ParsedRecords) async throws -> Int {
        var totalChanges = 0
        try await dbQueue.inTransaction { db in
            // Find existing patient or insert a new one
            var patientToSave = records.patient
            if let existing = try Patient.filter(Column("mrn") == patientToSave.mrn && Column("givenName") == patientToSave.givenName && Column("dob") == patientToSave.dob).fetchOne(db) {
                patientToSave.id = existing.id
            } else {
                _ = try patientToSave.insert(db, onConflict: .ignore)
                // Fetch the newly inserted patient to get their ID
                if let newPatient = try Patient.filter(Column("mrn") == patientToSave.mrn && Column("givenName") == patientToSave.givenName && Column("dob") == patientToSave.dob).fetchOne(db) {
                    patientToSave.id = newPatient.id
                }
            }

            guard let patientId = patientToSave.id else {
                throw GRDB.DatabaseError(message: "Could not find or create patient record.")
            }
            
            let beforeChanges = db.totalChangesCount
            
            try self.insert(records.allergies, for: patientId, in: db)
            try self.insert(records.problems, for: patientId, in: db)
            try self.insert(records.medications, for: patientId, in: db)
            try self.insert(records.immunizations, for: patientId, in: db)
            try self.insert(records.vitals, for: patientId, in: db)
            try self.insert(records.results, for: patientId, in: db)
            try self.insert(records.procedures, for: patientId, in: db)
            try self.insert(records.notes, for: patientId, in: db)
            
            totalChanges = db.totalChangesCount - beforeChanges
            return .commit
        }
        return totalChanges
    }

    /// Helper function to insert an array of medical records for a given patient.
    private func insert<T: MedicalRecord>(_ records: [T], for patientId: Int64, in db: Database) throws {
        for var record in records {
            record.patientId = patientId
            _ = try record.insert(db, onConflict: .ignore)
        }
    }
    
    /// Reads the database's internal schema and returns a formatted string.
    /// - Returns: A string describing all user-created tables and their columns.
    func getSchema() throws -> String {
        try dbQueue.read { db in
            let tables = try String.fetchAll(db, sql: "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").sorted()
            
            var schemaString = ""
            for table in tables {
                let columns = try db.columns(in: table)
                let columnNames = columns.map { $0.name }.joined(separator: ", ")
                schemaString += "Table: \(table)\nColumns: \(columnNames)\n\n"
            }
            return schemaString
        }
    }
    
    /// Executes a series of raw SQL queries against the database.
    /// - Parameter queries: An array of SQL query strings.
    /// - Returns: A formatted string containing the results of each query.
    func executeQueries(_ queries: [String]) async throws -> String {
        var allResults: [String] = []
        // This logic assumes a single patient's data is in the DB.
        // For multi-patient DBs, the query logic might need adjustment.
        let patientId = try await dbQueue.read { db in
            try Patient.fetchOne(db)?.id
        }
        
        guard let patientId = patientId else {
            return "Error: No patient found in database."
        }

        try await dbQueue.read { db in
            for query in queries {
                do {
                    // Use statement arguments to safely bind the patientId if a '?' placeholder exists
                    let arguments: StatementArguments = query.contains("?") ? [patientId] : []
                    let cursor = try Row.fetchCursor(db, sql: query, arguments: arguments)
                    
                    var header: String?
                    var rows: [String] = []
                    while let row = try cursor.next() {
                        if header == nil {
                            header = row.columnNames.joined(separator: " | ")
                        }
                        let rowValues = row.databaseValues.map { $0.isNull ? "NULL" : "\($0.storage.value ?? "")" }
                        rows.append(rowValues.joined(separator: " | "))
                    }
                    
                    if let header = header {
                        let resultHeader = "--- Query: \(query) ---\n\(header)"
                        let resultBody = rows.joined(separator: "\n")
                        allResults.append("\(resultHeader)\n\(resultBody)")
                    }
                } catch {
                    allResults.append("--- Error running query: \(query) ---\nError: \(error.localizedDescription)")
                }
            }
        }
        return allResults.isEmpty ? "Queries ran but returned no data." : allResults.joined(separator: "\n\n")
    }

    /// Fetches the entire clinical record, assuming only one patient exists in the DB.
    func fetchAllRecords() async throws -> ClinicalRecord? {
        try await dbQueue.read { db in
            guard let patient = try Patient.fetchOne(db) else {
                return nil // No patient found
            }
            
            let patientId = patient.id!
            
            // Fetch all related records
            let allergies = try Allergy.filter(Column("patientId") == patientId).fetchAll(db)
            let problems = try Problem.filter(Column("patientId") == patientId).fetchAll(db)
            let medications = try Medication.filter(Column("patientId") == patientId).fetchAll(db)
            let immunizations = try Immunization.filter(Column("patientId") == patientId).fetchAll(db)
            let vitals = try Vital.filter(Column("patientId") == patientId).fetchAll(db)
            let results = try LabResult.filter(Column("patientId") == patientId).fetchAll(db)
            let procedures = try Procedure.filter(Column("patientId") == patientId).fetchAll(db)
            let notes = try Note.filter(Column("patientId") == patientId).fetchAll(db)

            return ClinicalRecord(
                patient: patient,
                allergies: allergies,
                problems: problems,
                medications: medications,
                immunizations: immunizations,
                vitals: vitals,
                results: results,
                procedures: procedures,
                notes: notes
            )
        }
    }
}
