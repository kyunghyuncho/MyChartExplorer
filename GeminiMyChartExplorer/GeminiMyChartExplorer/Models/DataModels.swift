// MedicalRecordModels.swift

// Imports the fundamental Swift library, providing basic data types, collections, and operating-system services.
import Foundation
// Imports the GRDB.swift library, a powerful toolkit for working with SQLite databases in Swift.
import GRDB

/**
 * A protocol that defines the common structure and behavior for all types of medical records.
 * By conforming to this protocol, each record type ensures it has an ID, a link to a patient,
 * and the necessary capabilities to be encoded/decoded (Codable) and saved/retrieved
 * from a GRDB database (FetchableRecord, PersistableRecord).
 */
protocol MedicalRecord: Codable, Identifiable, FetchableRecord, PersistableRecord {
    // The unique identifier for the record. It's optional because a new record might not have an ID until it's saved to the database.
    var id: Int64? { get set }
    // The foreign key linking this record to a specific patient.
    var patientId: Int64? { get set }
}

/**
 * A structure to temporarily hold medical records as they are being parsed from an external source.
 * This acts as a container that collects all the different pieces of a patient's record
 * and can also capture any error that might occur during the parsing process.
 */
struct ParsedRecords {
    // The patient data being parsed.
    var patient: Patient
    // An array to hold parsed allergy records.
    var allergies: [Allergy] = []
    // An array to hold parsed medical problem records.
    var problems: [Problem] = []
    // An array to hold parsed medication records.
    var medications: [Medication] = []
    // An array to hold parsed immunization records.
    var immunizations: [Immunization] = []
    // An array to hold parsed vital sign records.
    var vitals: [Vital] = []
    // An array to hold parsed lab result records.
    var results: [LabResult] = []
    // An array to hold parsed medical procedure records.
    var procedures: [Procedure] = []
    // An array to hold parsed clinical notes.
    var notes: [Note] = []
    // An optional property to store any error encountered during parsing. Defaults to nil.
    var error: Error? = nil
}

// MARK: - Database Models

/**
 * Represents a single patient. This structure maps directly to the `patients` table in the database.
 * It conforms to Codable for data serialization, FetchableRecord and PersistableRecord for database operations,
 * and Identifiable for easy use in SwiftUI lists.
 */
struct Patient: Codable, FetchableRecord, PersistableRecord, Identifiable {
    // Primary key in the database.
    var id: Int64?
    // Medical Record Number, a unique identifier for the patient within a healthcare system.
    var mrn: String?
    // Patient's first name.
    var givenName: String?
    // Patient's last name.
    var familyName: String?
    // Patient's date of birth.
    var dob: String?
    // Patient's gender.
    var gender: String?
    // Patient's marital status.
    var maritalStatus: String?
    // Patient's race.
    var race: String?
    // Patient's ethnicity.
    var ethnicity: String?
    // A boolean flag indicating if the patient is deceased.
    var deceased: Bool?
    // The date the patient was marked as deceased.
    var deceasedDate: String?

    /// A computed property that combines the given and family names into a full name.
    /// It handles optional values gracefully and trims any extra whitespace.
    var fullName: String {
        return "\(givenName ?? "") \(familyName ?? "")".trimmingCharacters(in: .whitespaces)
    }
    
    // Explicitly tells GRDB that this model corresponds to the "patients" table.
    static var databaseTableName = "patients"
}

/**
 * Represents a single allergy record for a patient.
 * Conforms to the MedicalRecord protocol, making it a standard database-persistable record.
 */
struct Allergy: MedicalRecord {
    // The unique ID for this allergy record.
    var id: Int64?
    // Foreign key linking to the Patient.
    var patientId: Int64?
    // The substance the patient is allergic to.
    var substance: String?
    // The reaction the patient has to the substance.
    var reaction: String?
    // The status of the allergy (e.g., "active", "inactive").
    var status: String?
    // The date the allergy was first recorded or became effective.
    var effectiveDate: String?
    
    // Links this model to the "allergies" database table.
    static var databaseTableName = "allergies"
}

/**
 * Represents a single health problem or diagnosis for a patient.
 * Conforms to the MedicalRecord protocol.
 */
struct Problem: MedicalRecord {
    // The unique ID for this problem record.
    var id: Int64?
    // Foreign key linking to the Patient.
    var patientId: Int64?
    // The name or description of the health problem.
    var problemName: String?
    // The current status of the problem (e.g., "active", "resolved").
    var status: String?
    // The date the problem was first diagnosed or began.
    var onsetDate: String?
    // The date the problem was resolved, if applicable.
    var resolvedDate: String?
    
    // Links this model to the "problems" database table.
    static var databaseTableName = "problems"
}

/**
 * Represents a single medication prescribed to a patient.
 * Conforms to the MedicalRecord protocol.
 */
struct Medication: MedicalRecord {
    // The unique ID for this medication record.
    var id: Int64?
    // Foreign key linking to the Patient.
    var patientId: Int64?
    // The name of the medication.
    var medicationName: String?
    // Instructions for taking the medication.
    var instructions: String?
    // The status of the prescription (e.g., "active", "completed").
    var status: String?
    // The date the patient started the medication.
    var startDate: String?
    // The date the patient stopped the medication.
    var endDate: String?
    
    // Links this model to the "medications" database table.
    static var databaseTableName = "medications"
}

/**
 * Represents a single immunization (vaccination) administered to a patient.
 * Conforms to the MedicalRecord protocol.
 */
struct Immunization: MedicalRecord {
    // The unique ID for this immunization record.
    var id: Int64?
    // Foreign key linking to the Patient.
    var patientId: Int64?
    // The name of the vaccine.
    var vaccineName: String?
    // The date the vaccine was administered.
    var dateAdministered: String?
    
    // Links this model to the "immunizations" database table.
    static var databaseTableName = "immunizations"
}

/**
 * Represents a single vital sign measurement for a patient (e.g., blood pressure, heart rate).
 * Conforms to the MedicalRecord protocol.
 */
struct Vital: MedicalRecord {
    // The unique ID for this vital sign record.
    var id: Int64?
    // Foreign key linking to the Patient.
    var patientId: Int64?
    // The type of vital sign measured (e.g., "Height", "Weight", "Blood Pressure").
    var vitalSign: String?
    // The measured value of the vital sign.
    var value: String?
    // The unit of measurement (e.g., "cm", "kg", "mmHg").
    var unit: String?
    // The date and time the measurement was taken.
    var effectiveDate: String?
    
    // Links this model to the "vitals" database table.
    static var databaseTableName = "vitals"
}

/**
 * Represents a single lab result for a patient.
 * Conforms to the MedicalRecord protocol.
 */
struct LabResult: MedicalRecord {
    // The unique ID for this lab result record.
    var id: Int64?
    // Foreign key linking to the Patient.
    var patientId: Int64?
    // The name of the lab test performed.
    var testName: String?
    // The result value of the test.
    var value: String?
    // The unit of measurement for the value.
    var unit: String?
    // The normal or expected range for the test result.
    var referenceRange: String?
    // Interpretation of the result (e.g., "Normal", "High", "Abnormal").
    var interpretation: String?
    // The date the lab sample was collected or the result became effective.
    var effectiveDate: String?
    
    // Links this model to the "results" database table.
    static var databaseTableName = "results"
}

/**
 * Represents a single medical procedure performed on a patient.
 * Conforms to the MedicalRecord protocol.
 */
struct Procedure: MedicalRecord {
    // The unique ID for this procedure record.
    var id: Int64?
    // Foreign key linking to the Patient.
    var patientId: Int64?
    // The name of the procedure.
    var procedureName: String?
    // The date the procedure was performed.
    var date: String?
    // The healthcare provider who performed the procedure.
    var provider: String?
    
    // Links this model to the "procedures" database table.
    static var databaseTableName = "procedures"
}

/**
 * Represents a single clinical note for a patient.
 * Conforms to the MedicalRecord protocol.
 */
struct Note: MedicalRecord {
    // The unique ID for this note record.
    var id: Int64?
    // Foreign key linking to the Patient.
    var patientId: Int64?
    // The type of note (e.g., "Progress Note", "Discharge Summary").
    var noteType: String?
    // The date the note was written.
    var noteDate: String?
    // The title or subject of the note.
    var noteTitle: String?
    // The full text content of the note.
    var noteContent: String?
    // The healthcare provider who wrote the note.
    var provider: String?
    
    // Links this model to the "notes" database table.
    static var databaseTableName = "notes"
}

/**
 * A container structure to hold a complete, structured clinical record for a single patient.
 * This is likely used to pass around the full set of a patient's data within the application
 * after it has been successfully retrieved from the database.
 */
struct ClinicalRecord {
    // The patient's demographic information.
    var patient: Patient?
    // A list of the patient's allergies.
    var allergies: [Allergy] = []
    // A list of the patient's health problems.
    var problems: [Problem] = []
    // A list of the patient's medications.
    var medications: [Medication] = []
    // A list of the patient's immunizations.
    var immunizations: [Immunization] = []
    // A list of the patient's vital sign measurements.
    var vitals: [Vital] = []
    // A list of the patient's lab results.
    var results: [LabResult] = []
    // A list of the patient's procedures.
    var procedures: [Procedure] = []
    // A list of the patient's clinical notes.
    var notes: [Note] = []
}

/**
 * Represents a single message within a chat interface.
 * Conforms to Identifiable to be easily used in SwiftUI lists.
 */
struct ChatMessage: Identifiable {
    // A unique identifier for each message instance, generated automatically.
    let id = UUID()
    // The role of the entity that created the message (e.g., user or assistant).
    let role: ChatRole
    // The text content of the message.
    let text: String
}

/**
 * An enumeration defining the possible roles of participants in a chat conversation.
 */
enum ChatRole {
    // Represents a message from the end-user.
    case user
    // Represents a message from the AI or chatbot.
    case assistant
    // Represents a system-level message, often used for instructions or context (not typically displayed).
    case system
}
