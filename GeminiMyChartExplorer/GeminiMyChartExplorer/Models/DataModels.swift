// MedicalRecordModels.swift

import Foundation
import GRDB

protocol MedicalRecord: Codable, Identifiable, FetchableRecord, PersistableRecord {
    var id: Int64? { get set }
    var patientId: Int64? { get set }
}

struct ParsedRecords {
    var patient: Patient
    var allergies: [Allergy] = []
    var problems: [Problem] = []
    var medications: [Medication] = []
    var immunizations: [Immunization] = []
    var vitals: [Vital] = []
    var results: [LabResult] = []
    var procedures: [Procedure] = []
    var notes: [Note] = []
    var error: Error? = nil
}

// MARK: - Database Models

struct Patient: Codable, FetchableRecord, PersistableRecord, Identifiable {
    var id: Int64?
    var mrn: String?
    var givenName: String?
    var familyName: String?
    var dob: String?
    var gender: String?
    var maritalStatus: String?
    var race: String?
    var ethnicity: String?
    var deceased: Bool?
    var deceasedDate: String?

    // A computed property to easily get the full name
    var fullName: String {
        return "\(givenName ?? "") \(familyName ?? "")".trimmingCharacters(in: .whitespaces)
    }
    
    static var databaseTableName = "patients"
}

struct Allergy: MedicalRecord {
    var id: Int64?
    var patientId: Int64?
    var substance: String?
    var reaction: String?
    var status: String?
    var effectiveDate: String?
    
    static var databaseTableName = "allergies"
}

struct Problem: MedicalRecord {
    var id: Int64?
    var patientId: Int64?
    var problemName: String?
    var status: String?
    var onsetDate: String?
    var resolvedDate: String?
    
    static var databaseTableName = "problems"
}

struct Medication: MedicalRecord {
    var id: Int64?
    var patientId: Int64?
    var medicationName: String?
    var instructions: String?
    var status: String?
    var startDate: String?
    var endDate: String?
    
    static var databaseTableName = "medications"
}

struct Immunization: MedicalRecord {
    var id: Int64?
    var patientId: Int64?
    var vaccineName: String?
    var dateAdministered: String?
    
    static var databaseTableName = "immunizations"
}

struct Vital: MedicalRecord {
    var id: Int64?
    var patientId: Int64?
    var vitalSign: String?
    var value: String?
    var unit: String?
    var effectiveDate: String?
    
    static var databaseTableName = "vitals"
}

struct LabResult: MedicalRecord {
    var id: Int64?
    var patientId: Int64?
    var testName: String?
    var value: String?
    var unit: String?
    var referenceRange: String?
    var interpretation: String?
    var effectiveDate: String?
    
    static var databaseTableName = "results"
}

struct Procedure: MedicalRecord {
    var id: Int64?
    var patientId: Int64?
    var procedureName: String?
    var date: String?
    var provider: String?
    
    static var databaseTableName = "procedures"
}

struct Note: MedicalRecord {
    var id: Int64?
    var patientId: Int64?
    var noteType: String?
    var noteDate: String?
    var noteTitle: String?
    var noteContent: String?
    var provider: String?
    
    static var databaseTableName = "notes"
}

struct ClinicalRecord {
    var patient: Patient?
    var allergies: [Allergy] = []
    var problems: [Problem] = []
    var medications: [Medication] = []
    var immunizations: [Immunization] = []
    var vitals: [Vital] = []
    var results: [LabResult] = []
    var procedures: [Procedure] = []
    var notes: [Note] = []
}

struct ChatMessage: Identifiable {
    let id = UUID()
    let role: ChatRole
    let text: String
}

enum ChatRole {
    case user, assistant, system
}
