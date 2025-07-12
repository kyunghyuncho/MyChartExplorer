import SwiftUI

@MainActor
class AdvisorViewModel: ObservableObject {
    @Published var conversation: [ChatMessage] = []
    @Published var isThinking: Bool = false
    @Published var retrievedDataForConfirmation: String = ""
    @Published var isAPIKeySet: Bool = false
    
    private var appState: AppState?
    private var geminiService: GeminiService?
    private var dbManager: DatabaseManager?
    private let keychainService = KeychainService()
    
    func setup(appState: AppState) {
        self.appState = appState
        loadAPIKey()
        
        if let dbPath = appState.databasePath {
            self.dbManager = DatabaseManager(path: dbPath.path)
        }
    }
    
    func loadAPIKey() {
        if let key = keychainService.loadAPIKey() {
            self.geminiService = GeminiService(apiKey: key)
            self.isAPIKeySet = true
            if self.conversation.isEmpty {
                self.conversation.append(ChatMessage(role: .system, text: "Welcome! API Key loaded from Keychain. Please describe your symptoms."))
            }
        } else {
            self.isAPIKeySet = false
        }
    }
    
    func saveAPIKey(key: String) {
        if keychainService.saveAPIKey(key) {
            loadAPIKey()
        } else {
            conversation.append(ChatMessage(role: .system, text: "Error: Could not save API key to Keychain."))
        }
    }
    
    func getInitialAdvice(for symptoms: String) {
        guard let dbManager = dbManager, let geminiService = geminiService else {
            conversation.append(ChatMessage(role: .system, text: "Error: Services not initialized. Check DB path and API Key."))
            return
        }
        
        isThinking = true
        conversation.append(ChatMessage(role: .user, text: symptoms))
        
        Task {
            do {
                let schema = try dbManager.getSchema()
                
                let categories = try await geminiService.getRelevantCategories(symptoms: symptoms, schema: schema)
                let queries = try await geminiService.getSQLQueries(categories: categories, schema: schema)
                var retrievedData = try await dbManager.executeQueries(queries)

                if retrievedData.contains("No known active problems") {
                    let sections = retrievedData.components(separatedBy: .newlines)
                    let filteredLines = sections.filter { !$0.contains("No known active problems") }
                    retrievedData = filteredLines.joined(separator: "\n")
                }

                // This now correctly populates the string that shows the panel
                self.retrievedDataForConfirmation = retrievedData
                
            } catch {
                conversation.append(ChatMessage(role: .system, text: "An error occurred: \(error.localizedDescription)"))
            }
            isThinking = false
        }
    }
    
    open func getFinalAdvice() {
        guard let geminiService = geminiService, let lastUserMessage = conversation.last(where: { $0.role == .user }) else { return }
        
        isThinking = true
        let symptoms = lastUserMessage.text
        
        // Clear the data to hide the panel before making the final request
        let confirmedData = self.retrievedDataForConfirmation
        self.retrievedDataForConfirmation = ""
        
        Task {
            do {
                let advice = try await geminiService.getFinalAdvice(symptoms: symptoms, context: confirmedData)
                conversation.append(ChatMessage(role: .assistant, text: advice))
            } catch {
                conversation.append(ChatMessage(role: .system, text: "Failed to get final advice: \(error.localizedDescription)"))
            }
            isThinking = false
        }
    }
    
    open func cancelAdvice() {
        // Clear the data to hide the panel
        self.retrievedDataForConfirmation = ""
        conversation.append(ChatMessage(role: .system, text: "Operation cancelled."))
        isThinking = false
    }
}
