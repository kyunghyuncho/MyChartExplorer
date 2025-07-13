// DatabaseManager.swift

// Imports the fundamental Swift library for core functionalities.
import Foundation
// Imports the GRDB library, which provides the tools for interacting with the SQLite database.
import GRDB

/// Manages all interactions with the SQLite database, including setup, creation, and data manipulation.
class DatabaseManager {
    /// The database queue, which provides serialized, thread-safe access to the database.
    let dbQueue: DatabaseQueue

    /// Initializes the DatabaseManager.
    /// - Parameter path: The file system path where the SQLite database file will be stored.
    init(path: String) {
        do {
            // Attempts to create or open a database queue at the specified path.
            dbQueue = try DatabaseQueue(path: path)
            // Calls the method to create the necessary tables if they don't already exist.
            try createTables()
        } catch {
            // If the database cannot be initialized or tables can't be created, the app will crash with a descriptive error.
            // This is a critical failure, as the app cannot function without its database.
            fatalError("Could not connect to or set up database: \(error)")
        }
    }
    
    /// Creates all the necessary tables in the database using a schema defined by the model types.
    /// It includes unique constraints on columns to prevent duplicate entries.
    public func createTables() throws {
        // Performs the table creation within a write transaction to ensure it's an atomic operation.
        try dbQueue.write { db in
            // Creates the 'patients' table.
            try db.create(table: Patient.databaseTableName, ifNotExists: true) { t in
                t.autoIncrementedPrimaryKey("id") // The primary key for the table.
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
                // Ensures that a patient cannot be inserted if another patient with the same MRN, name, and DOB already exists.
                t.uniqueKey(["mrn", "givenName", "familyName", "dob"])
            }
            
            // Creates the 'allergies' table.
            try db.create(table: Allergy.databaseTableName, ifNotExists: true) { t in
                t.autoIncrementedPrimaryKey("id")
                // Defines a foreign key relationship to the 'patients' table. If a patient is deleted, their allergies are also deleted (cascade).
                t.column("patientId", .integer).notNull().references(Patient.databaseTableName, onDelete: .cascade)
                t.column("substance", .text)
                t.column("reaction", .text)
                t.column("status", .text)
                t.column("effectiveDate", .text)
                // Prevents duplicate allergy entries for the same patient, substance, and date.
                t.uniqueKey(["patientId", "substance", "effectiveDate"])
            }
            
            // Creates the 'problems' table.
            try db.create(table: Problem.databaseTableName, ifNotExists: true) { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("patientId", .integer).notNull().references(Patient.databaseTableName, onDelete: .cascade)
                t.column("problemName", .text)
                t.column("status", .text)
                t.column("onsetDate", .text)
                t.column("resolvedDate", .text)
                // Prevents duplicate problem entries for the same patient, problem name, and onset date.
                t.uniqueKey(["patientId", "problemName", "onsetDate"])
            }
            
            // Creates the 'medications' table.
            try db.create(table: Medication.databaseTableName, ifNotExists: true) { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("patientId", .integer).notNull().references(Patient.databaseTableName, onDelete: .cascade)
                t.column("medicationName", .text)
                t.column("instructions", .text)
                t.column("status", .text)
                t.column("startDate", .text)
                t.column("endDate", .text)
                // Prevents duplicate medication entries for the same patient, medication, and start date.
                t.uniqueKey(["patientId", "medicationName", "startDate"])
            }
            
            // Creates the 'immunizations' table.
            try db.create(table: Immunization.databaseTableName, ifNotExists: true) { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("patientId", .integer).notNull().references(Patient.databaseTableName, onDelete: .cascade)
                t.column("vaccineName", .text)
                t.column("dateAdministered", .text)
                // Prevents duplicate immunization entries for the same patient, vaccine, and date.
                t.uniqueKey(["patientId", "vaccineName", "dateAdministered"])
            }
            
            // Creates the 'vitals' table.
            try db.create(table: Vital.databaseTableName, ifNotExists: true) { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("patientId", .integer).notNull().references(Patient.databaseTableName, onDelete: .cascade)
                t.column("vitalSign", .text)
                t.column("value", .text)
                t.column("unit", .text)
                t.column("effectiveDate", .text)
                // Prevents duplicate vital entries for the same patient, vital sign, and date.
                t.uniqueKey(["patientId", "vitalSign", "effectiveDate"])
            }
            
            // Creates the 'results' table (for lab results).
            try db.create(table: LabResult.databaseTableName, ifNotExists: true) { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("patientId", .integer).notNull().references(Patient.databaseTableName, onDelete: .cascade)
                t.column("testName", .text)
                t.column("value", .text)
                t.column("unit", .text)
                t.column("referenceRange", .text)
                t.column("interpretation", .text)
                t.column("effectiveDate", .text)
                // Prevents duplicate lab result entries for the same patient, test, and date.
                t.uniqueKey(["patientId", "testName", "effectiveDate"])
            }
            
            // Creates the 'procedures' table.
            try db.create(table: Procedure.databaseTableName, ifNotExists: true) { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("patientId", .integer).notNull().references(Patient.databaseTableName, onDelete: .cascade)
                t.column("procedureName", .text)
                t.column("date", .text)
                t.column("provider", .text)
                // Prevents duplicate procedure entries for the same patient, procedure, and date.
                t.uniqueKey(["patientId", "procedureName", "date"])
            }
            
            // Creates the 'notes' table.
            try db.create(table: Note.databaseTableName, ifNotExists: true) { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("patientId", .integer).notNull().references(Patient.databaseTableName, onDelete: .cascade)
                t.column("noteType", .text)
                t.column("noteDate", .text)
                t.column("noteTitle", .text)
                t.column("noteContent", .text)
                t.column("provider", .text)
                // Prevents duplicate note entries for the same patient, date, and title.
                t.uniqueKey(["patientId", "noteDate", "noteTitle"])
            }
        }
    }

    /// Inserts a collection of parsed medical records into the database within a single transaction.
    /// It handles finding or creating the patient and then inserting all related records, ignoring any duplicates.
    /// - Parameter records: The `ParsedRecords` object containing all the data to be inserted.
    /// - Returns: The total number of new rows successfully inserted across all tables.
    func insertData(_ records: ParsedRecords) async throws -> Int {
        var totalChanges = 0
        // Using a transaction ensures that all database modifications are committed together, or none at all if an error occurs.
        try await dbQueue.inTransaction { db in
            // First, handle the patient record.
            var patientToSave = records.patient
            // Check if a patient with the same unique identifiers already exists.
            if let existing = try Patient.filter(Column("mrn") == patientToSave.mrn && Column("givenName") == patientToSave.givenName && Column("dob") == patientToSave.dob).fetchOne(db) {
                // If the patient exists, use their existing ID for associations.
                patientToSave.id = existing.id
            } else {
                // If the patient does not exist, insert them. The 'onConflict: .ignore' handles the unique key constraint gracefully.
                _ = try patientToSave.insert(db, onConflict: .ignore)
                // After inserting, fetch the new patient record to get their generated ID.
                if let newPatient = try Patient.filter(Column("mrn") == patientToSave.mrn && Column("givenName") == patientToSave.givenName && Column("dob") == patientToSave.dob).fetchOne(db) {
                    patientToSave.id = newPatient.id
                }
            }

            // Ensure we have a valid patient ID before proceeding.
            guard let patientId = patientToSave.id else {
                throw GRDB.DatabaseError(message: "Could not find or create patient record.")
            }
            
            // Record the number of changes before inserting the child records.
            let beforeChanges = db.totalChangesCount
            
            // Insert all the related medical records using the helper function.
            try self.insert(records.allergies, for: patientId, in: db)
            try self.insert(records.problems, for: patientId, in: db)
            try self.insert(records.medications, for: patientId, in: db)
            try self.insert(records.immunizations, for: patientId, in: db)
            try self.insert(records.vitals, for: patientId, in: db)
            try self.insert(records.results, for: patientId, in: db)
            try self.insert(records.procedures, for: patientId, in: db)
            try self.insert(records.notes, for: patientId, in: db)
            
            // Calculate the total number of new rows inserted in this transaction.
            totalChanges = db.totalChangesCount - beforeChanges
            return .commit // Commit the transaction.
        }
        return totalChanges
    }

    /// A generic helper function to insert an array of any type conforming to `MedicalRecord`.
    /// - Parameters:
    ///   - records: An array of record objects to insert.
    ///   - patientId: The ID of the patient to associate these records with.
    ///   - db: The database connection to use for the insertion.
    private func insert<T: MedicalRecord>(_ records: [T], for patientId: Int64, in db: Database) throws {
        for var record in records {
            // Assign the patient's ID to the record before insertion.
            record.patientId = patientId
            // Insert the record. `onConflict: .ignore` tells GRDB to do nothing if a record with the same unique key already exists.
            _ = try record.insert(db, onConflict: .ignore)
        }
    }
    
    /// Reads the database's schema and returns it as a formatted string.
    /// This is useful for providing context to an AI model about the database structure.
    /// - Returns: A string describing all user-defined tables and their columns.
    func getSchema() throws -> String {
        try dbQueue.read { db in
            // Fetches the names of all tables, excluding SQLite's internal system tables.
            let tables = try String.fetchAll(db, sql: "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").sorted()
            
            var schemaString = ""
            // Iterate over each table to get its column details.
            for table in tables {
                let columns = try db.columns(in: table)
                let columnNames = columns.map { $0.name }.joined(separator: ", ")
                schemaString += "Table: \(table)\nColumns: \(columnNames)\n\n"
            }
            return schemaString
        }
    }
    
    /// Executes a series of raw SQL queries and returns the results as a single formatted string.
    /// - Parameter queries: An array of SQL query strings to execute.
    /// - Returns: A formatted string containing the results of all queries.
    func executeQueries(_ queries: [String]) async throws -> String {
        var allResults: [String] = []
        // This implementation assumes there is only one patient in the database.
        // For a multi-patient system, queries would need to be more specific.
        let patientId = try await dbQueue.read { db in
            try Patient.fetchOne(db)?.id
        }
        
        // If no patient is found, no queries can be run.
        guard let patientId = patientId else {
            return "Error: No patient found in database."
        }

        try await dbQueue.read { db in
            for query in queries {
                do {
                    // Use statement arguments to safely bind the patientId, preventing SQL injection.
                    // This looks for a '?' placeholder in the query string.
                    let arguments: StatementArguments = query.contains("?") ? [patientId] : []
                    let cursor = try Row.fetchCursor(db, sql: query, arguments: arguments)
                    
                    var header: String?
                    var rows: [String] = []
                    // Iterate through each row in the result set.
                    while let row = try cursor.next() {
                        // Create the header from column names on the first row.
                        if header == nil {
                            header = row.columnNames.joined(separator: " | ")
                        }
                        // Format the row's values into a single string.
                        let rowValues = row.databaseValues.map { $0.isNull ? "NULL" : "\($0.storage.value ?? "")" }
                        rows.append(rowValues.joined(separator: " | "))
                    }
                    
                    // If the query returned results, format them for display.
                    if let header = header {
                        let resultHeader = "--- Query: \(query) ---\n\(header)"
                        let resultBody = rows.joined(separator: "\n")
                        allResults.append("\(resultHeader)\n\(resultBody)")
                    }
                } catch {
                    // If a query fails, append an error message to the results.
                    allResults.append("--- Error running query: \(query) ---\nError: \(error.localizedDescription)")
                }
            }
        }
        return allResults.isEmpty ? "Queries ran but returned no data." : allResults.joined(separator: "\n\n")
    }

    /// Fetches a complete, structured clinical record for the single patient assumed to be in the database.
    /// - Returns: An optional `ClinicalRecord` object containing all of the patient's data. Returns `nil` if no patient is found.
    func fetchAllRecords() async throws -> ClinicalRecord? {
        try await dbQueue.read { db in
            // First, try to fetch the patient.
            guard let patient = try Patient.fetchOne(db) else {
                return nil // No patient in the database.
            }
            
            let patientId = patient.id!
            
            // Fetch all records associated with the patient's ID.
            let allergies = try Allergy.filter(Column("patientId") == patientId).fetchAll(db)
            let problems = try Problem.filter(Column("patientId") == patientId).fetchAll(db)
            let medications = try Medication.filter(Column("patientId") == patientId).fetchAll(db)
            let immunizations = try Immunization.filter(Column("patientId") == patientId).fetchAll(db)
            let vitals = try Vital.filter(Column("patientId") == patientId).fetchAll(db)
            let results = try LabResult.filter(Column("patientId") == patientId).fetchAll(db)
            let procedures = try Procedure.filter(Column("patientId") == patientId).fetchAll(db)
            let notes = try Note.filter(Column("patientId") == patientId).fetchAll(db)

            // Assemble the complete record into the ClinicalRecord struct.
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
