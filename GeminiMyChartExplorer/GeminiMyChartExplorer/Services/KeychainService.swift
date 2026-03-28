// Imports the fundamental Swift library for core functionalities.
import Foundation
// Imports the Security framework, which is necessary for interacting with the iOS Keychain.
import Security

/// A struct that provides simple methods for securely saving and loading an API key using the iOS Keychain.
/// The Keychain is a secure, encrypted container for storing small pieces of sensitive data.
struct KeychainService {
    /// A unique identifier for your app's keychain items. It's best practice to use your app's bundle identifier
    /// to avoid conflicts with other apps.
    private let service = "com.example.MedicalAdvisor" // IMPORTANT: This should be changed to your app's unique bundle ID.
    /// A specific key for the piece of data being stored. This distinguishes it from other data your app might save.
    private let account = "geminiAPIKey"

    /// Saves a given API key string to the Keychain.
    /// - Parameter key: The API key string to be saved.
    /// - Returns: A boolean value indicating whether the save operation was successful.
    func saveAPIKey(_ key: String) -> Bool {
        // First, convert the string key into a Data object using UTF-8 encoding.
        guard let data = key.data(using: .utf8) else { return false }

        // Create a query dictionary to specify what to save and where.
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,   // Specifies the item is a generic password.
            kSecAttrService as String: service,              // The service identifier for your app.
            kSecAttrAccount as String: account,              // The specific account name for this piece of data.
            kSecValueData as String: data                    // The actual data to be stored.
        ]
        
        // Before adding the new key, it's good practice to delete any old item with the same service and account.
        // This prevents errors if you try to add an item that already exists.
        SecItemDelete(query as CFDictionary)
        
        // Add the new item to the Keychain.
        let status = SecItemAdd(query as CFDictionary, nil)
        
        // Return true if the operation completed successfully.
        return status == errSecSuccess
    }

    /// Loads the API key string from the Keychain.
    /// - Returns: An optional String containing the API key if it's found, otherwise nil.
    func loadAPIKey() -> String? {
        // Create a query dictionary to specify what to search for.
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: kCFBooleanTrue!,      // We want the actual data to be returned.
            kSecMatchLimit as String: kSecMatchLimitOne      // We only expect to find one matching item.
        ]
        
        // A reference that will hold the data retrieved from the Keychain.
        var dataTypeRef: AnyObject?
        
        // Perform the search operation by matching the query.
        let status = SecItemCopyMatching(query as CFDictionary, &dataTypeRef)
        
        // If the operation was successful and the retrieved data can be cast to a Data object...
        if status == errSecSuccess, let retrievedData = dataTypeRef as? Data {
            // ...convert the Data object back into a String and return it.
            return String(data: retrievedData, encoding: .utf8)
        }
        
        // If the item wasn't found or an error occurred, return nil.
        return nil
    }
}
