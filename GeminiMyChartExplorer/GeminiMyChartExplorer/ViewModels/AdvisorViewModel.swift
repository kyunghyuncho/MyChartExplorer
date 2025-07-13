import SwiftUI

/// An enumeration to define the available AI services that the user can select.
/// It conforms to `CaseIterable` to easily list all cases, and `Identifiable` for use in SwiftUI views.
enum AiServiceType: String, CaseIterable, Identifiable {
    case gemini = "Gemini (Remote)"
    case ollama = "Ollama (Local)"
    /// The stable identity of the enumeration case, required by `Identifiable`.
    var id: Self { self }
}

/// The main view model for the advisor interface, responsible for managing state,
/// handling user interactions, and coordinating with the various services (AI, database, keychain).
/// It is marked with `@MainActor` to ensure that all UI updates happen on the main thread.
@MainActor
class AdvisorViewModel: ObservableObject {
    // MARK: - Published Properties for UI State
    
    /// The array of chat messages that make up the current conversation.
    @Published var conversation: [ChatMessage] = []
    /// A boolean flag to indicate when the AI is processing a request, used to show loading indicators.
    @Published var isThinking: Bool = false
    /// A string containing the summarized data retrieved from the database, presented to the user for confirmation.
    @Published var retrievedDataForConfirmation: String = ""
    /// A boolean flag indicating whether the Gemini API key has been successfully loaded from the Keychain.
    @Published var isAPIKeySet: Bool = false
    
    /// The summarized data (primarily notes) that is safe to display in the UI.
    @Published var dataForDisplay: String = ""
    /// The full, potentially more detailed context (with summarized notes) to be sent to the AI for final advice.
    @Published var fullContextForAdvice: String = ""

    /// The currently selected AI service type, controlled by a picker in the UI.
    /// When this property changes, the `didSet` observer calls `updateServiceState` to reset the UI.
    @Published var selectedService: AiServiceType = .gemini {
        didSet {
            updateServiceState()
        }
    }
    
    // MARK: - Private Properties
    
    /// A reference to the global app state.
    private var appState: AppState?
    /// The manager for handling all database interactions.
    private var dbManager: DatabaseManager?
    /// The service for securely saving and loading the API key from the Keychain.
    private let keychainService = KeychainService()
    
    /// An instance of the `GeminiService`. It's optional because it requires an API key to be initialized.
    private var geminiService: GeminiService?
    /// An instance of the `OllamaService`. It can be initialized immediately as it doesn't require a key.
    private var ollamaService: OllamaService?
    
    /// A computed property that returns the currently active `AdvisingService` based on the user's selection
    /// and whether the required setup (like an API key) is complete.
    private var activeService: AdvisingService? {
        switch selectedService {
        case .gemini:
            // Gemini service is only active if the API key is set.
            return self.isAPIKeySet ? self.geminiService : nil
        case .ollama:
            // Ollama service is always considered active if selected.
            return self.ollamaService
        }
    }
    
    /// A computed property that provides a simple boolean to the View, indicating if the selected AI service is ready to be used.
    var isServiceReady: Bool {
        return activeService != nil
    }

    /// Sets up the view model with necessary dependencies from the main app state.
    /// - Parameter appState: The shared application state.
    func setup(appState: AppState) {
        self.appState = appState
        self.ollamaService = OllamaService() // Ollama can be initialized without any configuration.
        loadAPIKey() // Attempt to load the Gemini API key from the Keychain.
        
        // Initialize the database manager if a valid path is available.
        if let dbPath = appState.databasePath {
            self.dbManager = DatabaseManager(path: dbPath.path)
        }
    }
    
    /// Resets the conversation and updates the initial system message based on the currently selected service's state.
    func updateServiceState() {
        conversation = [] // Clear the previous conversation.
        let welcomeMessage: String
        
        switch selectedService {
        case .gemini:
            welcomeMessage = isAPIKeySet ? "Service changed to Gemini (Remote). Please describe your symptoms." : "Gemini service requires an API key. Please enter it below."
        case .ollama:
            welcomeMessage = "Service changed to Ollama (Local). Please describe your symptoms."
        }
        conversation.append(ChatMessage(role: .system, text: welcomeMessage))
    }
    
    /// Attempts to load the Gemini API key from the Keychain and updates the service state accordingly.
    func loadAPIKey() {
        if let key = keychainService.loadAPIKey() {
            // If a key is found, initialize the Gemini service with it.
            self.geminiService = GeminiService(apiKey: key)
            self.isAPIKeySet = true
        } else {
            self.isAPIKeySet = false
        }
        updateServiceState() // Refresh the UI state after loading the key.
    }
    
    /// Saves a new Gemini API key to the Keychain and reloads the service.
    /// - Parameter key: The API key string to save.
    func saveAPIKey(key: String) {
        if keychainService.saveAPIKey(key) {
            loadAPIKey() // If saving is successful, immediately load the key to activate the service.
        } else {
            conversation.append(ChatMessage(role: .system, text: "Error: Could not save API key to Keychain."))
        }
    }
    
    /// Starts the multi-step process of getting advice based on user-reported symptoms.
    /// - Parameter symptoms: The user's initial input describing their symptoms.
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
                // Step 1: Get the database schema.
                let schema = try dbManager.getSchema()
                // Step 2: Ask the AI to determine relevant data categories.
                let categories = try await service.getRelevantCategories(symptoms: symptoms, schema: schema)
                // Step 3: Ask the AI to generate SQL queries for those categories.
                let queries = try await service.getSQLQueries(categories: categories, schema: schema)
                
                // Step 4: Execute the queries against the local database.
                let rawData = try await dbManager.executeQueries(queries)
                
                // Step 5: Send the raw data to the AI service for processing (e.g., summarizing notes).
                let processedResult = try await service.processDBResults(results: rawData, symptoms: symptoms)

                // Step 6: Store the processed results, ready for user confirmation and the final advice step.
                self.fullContextForAdvice = processedResult.fullContext
                self.dataForDisplay = processedResult.notesForDisplay
            } catch {
                conversation.append(ChatMessage(role: .system, text: "An error occurred: \(error.localizedDescription)"))
            }
            isThinking = false
        }
    }

    /// Proceeds to get the final, formatted advice from the AI after the user has confirmed the retrieved data.
    func getFinalAdvice() {
        guard let service = activeService, let lastUserMessage = conversation.last(where: { $0.role == .user }) else { return }
        
        isThinking = true
        let symptoms = lastUserMessage.text
        // Use the full context (which includes summarized notes) for the final AI call.
        let contextForAI = self.fullContextForAdvice
        
        // Clear the properties to hide the confirmation panel in the UI.
        self.dataForDisplay = ""
        self.fullContextForAdvice = ""

        Task {
            do {
                // Ask the AI for the final, user-facing advice.
                let advice = try await service.getFinalAdvice(symptoms: symptoms, context: contextForAI)
                conversation.append(ChatMessage(role: .assistant, text: advice))
            } catch {
                conversation.append(ChatMessage(role: .system, text: "Failed to get final advice: \(error.localizedDescription)"))
            }
            isThinking = false
        }
    }
    
    /// Cancels the advice process, clearing any data pending confirmation.
    func cancelAdvice() {
        self.dataForDisplay = ""
        self.fullContextForAdvice = ""
        conversation.append(ChatMessage(role: .system, text: "Operation cancelled."))
        isThinking = false
    }
    
    /// Completely resets the view model to its initial state.
    func resetConversation() {
        isThinking = false
        
        // Clear any data that was waiting for confirmation.
        dataForDisplay = ""
        fullContextForAdvice = ""
        
        // This existing function clears the conversation array and adds the appropriate welcome message.
        updateServiceState()
    }
}
