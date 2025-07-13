import SwiftUI

/// The main SwiftUI view for the Medical Advisor feature.
/// It handles the overall layout, user input, and displays the conversation,
/// conditionally showing views for database status or API key entry when needed.
struct AdvisorView: View {
    // MARK: - Environment and State
    
    /// Access to the global application state, used here to check if the database is ready.
    @EnvironmentObject var appState: AppState
    /// The view model that drives this view, containing all the state and logic for the advisor.
    @StateObject private var viewModel: AdvisorViewModel
    
    /// State for the text currently being typed by the user in the input field.
    @State private var userMessage: String = ""
    /// State for the text being typed into the secure field for the API key.
    @State private var apiKeyInput: String = ""
    /// A focus state variable to programmatically control the focus of the text input field.
    @FocusState private var isAdvisorFocused: Bool

    /// Custom initializer required when using `@StateObject` to pass a pre-initialized view model.
    @MainActor
    init(viewModel: AdvisorViewModel) {
        _viewModel = StateObject(wrappedValue: viewModel)
    }

    // MARK: - Body
    
    var body: some View {
        VStack(spacing: 0) {
            // Conditionally render the main content based on the app's state.
            if !appState.isDatabaseReady {
                // Show a placeholder if no database has been created or loaded.
                PlaceholderView(
                    imageName: "icloud.slash",
                    title: "Database Not Ready",
                    subtitle: "Please go to the 'Importer' tab to create or open a database file."
                )
            } else if !viewModel.isServiceReady {
                // Show the API key entry view if the selected service (Gemini) is not ready.
                apiKeyEntryView
            } else {
                // Show the main chat interface.
                mainContentView
            }
        }
        .navigationTitle("Medical Advisor")
        .toolbar {
            // Toolbar item for the AI service selection picker.
            ToolbarItem(placement: .navigation) {
                Picker("Service", selection: $viewModel.selectedService) {
                    ForEach(AiServiceType.allCases) { service in
                        Text(service.rawValue).tag(service)
                    }
                }
                .pickerStyle(.segmented)
                .frame(width: 240)
            }
            
            // Toolbar item for the reset conversation button.
            ToolbarItem {
                Button(action: {
                    viewModel.resetConversation()
                }) {
                    Label("Reset Conversation", systemImage: "arrow.counterclockwise")
                }
                .help("Reset Conversation") // Tooltip for macOS.
            }
        }
        .onAppear {
            // When the view appears, set up the view model and set the initial focus.
            viewModel.setup(appState: appState)
            isAdvisorFocused = true
        }
        // This hidden text field is a workaround to allow programmatic focus control
        // on the main view area, ensuring keyboard input is captured correctly.
        .overlay(
            TextField("", text: .constant(""))
                .focused($isAdvisorFocused)
                .opacity(0)
        )
    }

    // MARK: - Subviews

    /// The primary layout container, splitting the chat interface from the data confirmation panel.
    private var mainContentView: some View {
        HSplitView {
            chatInterface
                .frame(minWidth: 400, maxWidth: .infinity, maxHeight: .infinity)

            // The data panel is only shown when there is data retrieved from the DB waiting for confirmation.
            if !viewModel.fullContextForAdvice.isEmpty {
                QueriedDataPanel(
                    rawText: viewModel.fullContextForAdvice,
                    onConfirm: viewModel.getFinalAdvice,
                    onCancel: viewModel.cancelAdvice
                )
                .frame(minWidth: 450, maxWidth: 600)
            }
        }
    }
    
    /// A view for entering the Gemini API key when it's required but not set.
    private var apiKeyEntryView: some View {
        PlaceholderView(
            imageName: "key.shield",
            title: "Gemini API Key Required",
            subtitle: "Please enter your API key to use the Advisor. It will be stored securely in your Keychain."
        ) {
            // A secure field to hide the API key as it's being typed.
            SecureField("Enter your Google AI Studio API key", text: $apiKeyInput)
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 400)

            Button("Save and Continue") {
                viewModel.saveAPIKey(key: apiKeyInput)
                apiKeyInput = "" // Clear the input field after saving.
            }
            .buttonStyle(.borderedProminent)
            .disabled(apiKeyInput.isEmpty)
            .controlSize(.large)
        }
    }

    /// The main chat interface, combining the history and the input bar.
    private var chatInterface: some View {
        VStack(spacing: 0) {
            chatHistoryView
            Divider()
            chatInputBar
        }
        // Ensures the input bar doesn't get pushed up by the on-screen keyboard.
        .ignoresSafeArea(.keyboard, edges: .bottom)
    }
    
    /// The scrollable view that displays the conversation history.
    private var chatHistoryView: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(spacing: 12) {
                    ForEach(viewModel.conversation) { msg in
                        MessageView(message: msg)
                    }
                }
                .padding()
                // An invisible anchor at the bottom of the scroll view.
                .id("bottom")
            }
            .background(Color(NSColor.windowBackgroundColor))
            // Whenever the number of messages changes, scroll to the bottom.
            .onChange(of: viewModel.conversation.count) {
                withAnimation {
                    proxy.scrollTo("bottom", anchor: .bottom)
                }
            }
        }
    }
    
    /// The input bar at the bottom of the screen with a text field and send button.
    private var chatInputBar: some View {
        HStack(spacing: 12) {
            TextField("Describe your symptoms...", text: $userMessage, axis: .vertical)
                .lineLimit(5) // Allow the text field to grow up to 5 lines.
                .textFieldStyle(.plain)
                .padding(10)
                .background(Color(NSColor.controlBackgroundColor))
                .clipShape(Capsule())
                .focused($isAdvisorFocused) // Bind the focus state.
                .onSubmit(sendMessage) // Allow sending by pressing Enter.
            
            Button(action: sendMessage) {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 28))
                    .symbolRenderingMode(.multicolor)
            }
            .buttonStyle(.plain)
            .tint(.accentColor)
            .disabled(userMessage.isEmpty || viewModel.isThinking)
            .keyboardShortcut(.return, modifiers: .command) // Cmd+Enter shortcut.

            // Show a progress spinner while the view model is thinking.
            if viewModel.isThinking {
                ProgressView()
                    .scaleEffect(0.8)
            }
        }
        .padding()
        .background(.regularMaterial)
    }
    
    // MARK: - Actions
    
    /// Trims and sends the user's message to the view model.
    private func sendMessage() {
        let messageToSend = userMessage.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !messageToSend.isEmpty else { return }
        
        viewModel.getInitialAdvice(for: messageToSend)
        userMessage = "" // Clear the input field.
    }
}


// MARK: - Subviews

/// A helper struct to hold the parsed results of a single SQL query for display.
struct QueryResultTable: Identifiable {
    let id = UUID()
    let title: String
    let headers: [String]
    let rows: [[String]]
}

/// A view that displays the data retrieved from the database in a series of tables,
/// and provides buttons for the user to confirm or cancel the operation.
private struct QueriedDataPanel: View {
    let tables: [QueryResultTable]
    let onConfirm: () -> Void
    let onCancel: () -> Void

    /// A custom initializer that takes the raw text from the ViewModel and parses it into structured tables.
    init(rawText: String, onConfirm: @escaping () -> Void, onCancel: @escaping () -> Void) {
        self.onConfirm = onConfirm
        self.onCancel = onCancel
        self.tables = Self.parseRawTextToTables(rawText)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Panel Header
            Text("Queried Medical Data")
                .font(.headline)
                .padding()
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(.regularMaterial)

            Divider()

            // Scrollable Content Area
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    ForEach(tables) { table in
                        VStack(alignment: .leading) {
                            Text(table.title)
                                .font(.caption.monospaced())
                                .foregroundStyle(.secondary)
                            
                            // Use a Grid for tabular data layout.
                            Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 8) {
                                // Header Row: Iterate over indices for stability.
                                GridRow {
                                    ForEach(0..<table.headers.count, id: \.self) { index in
                                        Text(table.headers[index])
                                            .font(.headline)
                                            .gridColumnAlignment(.leading)
                                    }
                                }
                                
                                // A divider that correctly spans all columns in the grid.
                                Divider()
                                    .gridCellColumns(table.headers.count)

                                // Data Rows: Also iterate over indices.
                                ForEach(0..<table.rows.count, id: \.self) { rowIndex in
                                    let row = table.rows[rowIndex]
                                    GridRow {
                                        ForEach(0..<row.count, id: \.self) { cellIndex in
                                            Text(row[cellIndex])
                                        }
                                    }
                                }
                            }
                            .padding(.top, 4)
                        }
                    }
                }
                .padding()
            }

            Divider()

            // Panel Footer with action buttons
            HStack {
                Spacer()
                Button("Cancel", role: .cancel, action: onCancel)
                    .keyboardShortcut(.cancelAction)

                Button("Confirm and Advise", action: onConfirm)
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.defaultAction)
            }
            .padding()
            .background(.regularMaterial)
        }
        .background(Color(NSColor.windowBackgroundColor))
    }

    /// A static helper function to parse the raw multi-line string from the AI/database into an array of table objects.
    private static func parseRawTextToTables(_ text: String) -> [QueryResultTable] {
        // Split the entire text block into sections, where each section begins with "--- Query:".
        let sections = text.components(separatedBy: "--- Query:").dropFirst()
        
        return sections.compactMap { section in
            // For each section, split it into individual lines.
            let lines = section.trimmingCharacters(in: .whitespacesAndNewlines).components(separatedBy: .newlines)
            guard !lines.isEmpty else { return nil }

            let title = "--- Query:" + lines.first!
            let remainingLines = lines.dropFirst()
            
            // A valid table needs at least a header and one row of data.
            guard remainingLines.count >= 2 else { return nil }
            
            // The first remaining line is the header. Split it by the "|" delimiter.
            let headers = remainingLines.first!.components(separatedBy: "|").map { $0.trimmingCharacters(in: .whitespaces) }
            // The rest of the lines are data rows.
            let dataRows = remainingLines.dropFirst().map { rowString in
                rowString.components(separatedBy: "|").map { $0.trimmingCharacters(in: .whitespaces) }
            }
            
            return QueryResultTable(title: title, headers: headers, rows: dataRows)
        }
    }
}
