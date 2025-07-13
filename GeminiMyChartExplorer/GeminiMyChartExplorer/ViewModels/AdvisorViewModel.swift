import SwiftUI

// Enum to define the available AI services
enum AiServiceType: String, CaseIterable, Identifiable {
    case gemini = "Gemini (Remote)"
    case ollama = "Ollama (Local)"
    var id: Self { self }
}

@MainActor
class AdvisorViewModel: ObservableObject {
    @Published var conversation: [ChatMessage] = []
    @Published var isThinking: Bool = false
    @Published var retrievedDataForConfirmation: String = ""
    @Published var isAPIKeySet: Bool = false
    
    @Published var dataForDisplay: String = ""
    @Published var fullContextForAdvice: String = ""

    // New property to control the service selection from the view
    @Published var selectedService: AiServiceType = .gemini {
        didSet {
            updateServiceState()
        }
    }
    
    private var appState: AppState?
    private var dbManager: DatabaseManager?
    private let keychainService = KeychainService()
    
    // Hold instances of both services
    private var geminiService: GeminiService?
    private var ollamaService: OllamaService?
    
    /// Computed property to return the currently active service
    private var activeService: AdvisingService? {
        switch selectedService {
        case .gemini:
            return self.isAPIKeySet ? self.geminiService : nil
        case .ollama:
            return self.ollamaService
        }
    }
    
    /// A computed property to simplify the logic in the View
    var isServiceReady: Bool {
        return activeService != nil
    }

    func setup(appState: AppState) {
        self.appState = appState
        self.ollamaService = OllamaService() // Ollama can be initialized immediately
        loadAPIKey() // This will load the key and then call updateServiceState()
        
        if let dbPath = appState.databasePath {
            self.dbManager = DatabaseManager(path: dbPath.path)
        }
    }
    
    /// Updates the conversation and state based on the selected service
    func updateServiceState() {
        conversation = [] // Clear conversation on service switch
        let welcomeMessage: String
        
        switch selectedService {
        case .gemini:
            welcomeMessage = isAPIKeySet ? "Service changed to Gemini (Remote). Please describe your symptoms." : "Gemini service requires an API key. Please enter it below."
        case .ollama:
            welcomeMessage = "Service changed to Ollama (Local). Please describe your symptoms."
        }
        conversation.append(ChatMessage(role: .system, text: welcomeMessage))
    }
    
    func loadAPIKey() {
        if let key = keychainService.loadAPIKey() {
            self.geminiService = GeminiService(apiKey: key)
            self.isAPIKeySet = true
        } else {
            self.isAPIKeySet = false
        }
        updateServiceState() // Update state after loading key
    }
    
    func saveAPIKey(key: String) {
        if keychainService.saveAPIKey(key) {
            loadAPIKey() // This will reload the key and update the state
        } else {
            conversation.append(ChatMessage(role: .system, text: "Error: Could not save API key to Keychain."))
        }
    }
    
    func getInitialAdvice(for symptoms: String) {
        guard let dbManager = dbManager, let service = activeService else {
            let errorMsg = selectedService == .gemini ? "Error: Gemini API Key not set." : "Error: Ollama service not available."
            conversation.append(ChatMessage(role: .system, text: errorMsg))
            return
        }
        
        isThinking = true
        conversation.append(ChatMessage(role: .user, text: symptoms))
        
        Task {
            do {
                let schema = try dbManager.getSchema()
                let categories = try await service.getRelevantCategories(symptoms: symptoms, schema: schema)
                let queries = try await service.getSQLQueries(categories: categories, schema: schema)
                
                // 1. Get the raw, potentially long data from the database
                let rawData = try await dbManager.executeQueries(queries)
                
                // 2. **(New Step)** Call the summarization service
                let processedResult = try await service.processDBResults(results: rawData, symptoms: symptoms)

                // 3. Set the summarized data for user confirmation.
                // Store the two different parts of the result
                self.fullContextForAdvice = processedResult.fullContext
                self.dataForDisplay = processedResult.notesForDisplay
            } catch {
                conversation.append(ChatMessage(role: .system, text: "An error occurred: \(error.localizedDescription)"))
            }
            isThinking = false
        }
    }

    func getFinalAdvice() {
        guard let service = activeService, let lastUserMessage = conversation.last(where: { $0.role == .user }) else { return }
        
        isThinking = true
        let symptoms = lastUserMessage.text
        let confirmedData = self.dataForDisplay // This is the summarized notes for display
        // [optional] Clear the properties to hide the panel
//        self.dataForDisplay = ""
//        self.fullContextForAdvice = ""

        Task {
            do {
                let advice = try await service.getFinalAdvice(symptoms: symptoms, context: confirmedData)
                conversation.append(ChatMessage(role: .assistant, text: advice))
            } catch {
                conversation.append(ChatMessage(role: .system, text: "Failed to get final advice: \(error.localizedDescription)"))
            }
            isThinking = false
        }
    }
    
    func cancelAdvice() {
        self.dataForDisplay = ""
        self.fullContextForAdvice = ""

        conversation.append(ChatMessage(role: .system, text: "Operation cancelled."))
        isThinking = false
    }
    
    /// Resets the conversation and all temporary state.
    func resetConversation() {
        // Stop any in-progress thinking
        isThinking = false
        
        // Clear any data waiting for confirmation
        dataForDisplay = ""
        fullContextForAdvice = ""
        
        // This existing function will clear the conversation array
        // and add the appropriate welcome message for the selected service.
        updateServiceState()
    }

}
