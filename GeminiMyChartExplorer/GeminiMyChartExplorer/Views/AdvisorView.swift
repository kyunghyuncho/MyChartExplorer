import SwiftUI

struct AdvisorView: View {
    @EnvironmentObject var appState: AppState
    @StateObject private var viewModel: AdvisorViewModel
    
    @State private var userMessage: String = ""
    @State private var apiKeyInput: String = ""
    @FocusState private var isAdvisorFocused: Bool

    @MainActor
    init(viewModel: AdvisorViewModel) {
        _viewModel = StateObject(wrappedValue: viewModel)
    }

    var body: some View {
        VStack(spacing: 0) {
            if !appState.isDatabaseReady {
                PlaceholderView(
                    imageName: "icloud.slash",
                    title: "Database Not Ready",
                    subtitle: "Please go to the 'Importer' tab to create or open a database file."
                )
            } else if !viewModel.isAPIKeySet {
                apiKeyEntryView
            } else {
                mainContentView
            }
        }
        .navigationTitle("Medical Advisor")
        .onAppear {
            viewModel.setup(appState: appState)
            isAdvisorFocused = true
        }
        .overlay(
            TextField("", text: .constant(""))
                .focused($isAdvisorFocused)
                .opacity(0)
        )
    }

    /// The primary layout container, splitting the chat from the data panel.
    private var mainContentView: some View {
        HSplitView {
            chatInterface
                .frame(minWidth: 400, maxWidth: .infinity, maxHeight: .infinity)

            if !viewModel.retrievedDataForConfirmation.isEmpty {
                QueriedDataPanel(
                    rawText: viewModel.retrievedDataForConfirmation,
                    onConfirm: viewModel.getFinalAdvice,
                    onCancel: viewModel.cancelAdvice
                )
                .frame(minWidth: 450, maxWidth: 600) // Adjusted width for better table display
            }
        }
    }
    
    /// A view for entering the API key.
    private var apiKeyEntryView: some View {
        PlaceholderView(
            imageName: "key.shield",
            title: "Gemini API Key Required",
            subtitle: "Please enter your API key to use the Advisor. It will be stored securely in your Keychain."
        ) {
            SecureField("Enter your Google AI Studio API key", text: $apiKeyInput)
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 400)

            Button("Save and Continue") {
                viewModel.saveAPIKey(key: apiKeyInput)
                apiKeyInput = ""
            }
            .buttonStyle(.borderedProminent)
            .disabled(apiKeyInput.isEmpty)
            .controlSize(.large)
        }
    }

    /// The main chat interface.
    private var chatInterface: some View {
        VStack(spacing: 0) {
            // 2. The view is now simpler, just calling the new property.
            chatHistoryView
            
            Divider()
            chatInputBar
        }
        .ignoresSafeArea(.keyboard, edges: .bottom)
    }
    
    // 👇 1. Create this new computed property to hold the complex ScrollView logic.
    private var chatHistoryView: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(spacing: 12) { // Adjusted spacing
                    // The ForEach loop is now much cleaner
                    ForEach(viewModel.conversation) { msg in
                        MessageView(message: msg)
                    }
                }
                .padding()
                .id("bottom")
            }
            .background(Color(NSColor.windowBackgroundColor))
            .onChange(of: viewModel.conversation.count) {
                withAnimation {
                    proxy.scrollTo("bottom", anchor: .bottom)
                }
            }
        }
    }
    
    /// The text input field and send button at the bottom.
    private var chatInputBar: some View {
        HStack(spacing: 12) {
            TextField("Describe your symptoms...", text: $userMessage, axis: .vertical)
                .lineLimit(5)
                .textFieldStyle(.plain)
                .padding(10)
                .background(Color(NSColor.controlBackgroundColor))
                .clipShape(Capsule())
                .focused($isAdvisorFocused)
                .onSubmit(sendMessage)
            
            Button(action: sendMessage) {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 28))
                    .symbolRenderingMode(.multicolor)
            }
            .buttonStyle(.plain)
            .tint(.accentColor)
            .disabled(userMessage.isEmpty || viewModel.isThinking)
            .keyboardShortcut(.return, modifiers: .command)

            if viewModel.isThinking {
                ProgressView()
                    .scaleEffect(0.8)
            }
        }
        .padding()
        .background(.regularMaterial)
    }
    
    private func sendMessage() {
        let messageToSend = userMessage.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !messageToSend.isEmpty else { return }
        
        viewModel.getInitialAdvice(for: messageToSend)
        userMessage = ""
    }
}


// MARK: - Subviews

/// A structure to hold the parsed results of a single SQL query.
struct QueryResultTable: Identifiable {
    let id = UUID()
    let title: String
    let headers: [String]
    let rows: [[String]]
}

private struct QueriedDataPanel: View {
    let tables: [QueryResultTable]
    let onConfirm: () -> Void
    let onCancel: () -> Void

    /// A custom initializer to parse the raw text from the ViewModel.
    init(rawText: String, onConfirm: @escaping () -> Void, onCancel: @escaping () -> Void) {
        self.onConfirm = onConfirm
        self.onCancel = onCancel
        self.tables = Self.parseRawTextToTables(rawText)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header (no changes here)
            Text("Queried Medical Data")
                .font(.headline)
                .padding()
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(.regularMaterial)

            Divider()

            // Content
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    ForEach(tables) { table in
                        VStack(alignment: .leading) {
                            Text(table.title)
                                .font(.caption.monospaced())
                                .foregroundStyle(.secondary)
                            
                            Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 8) {
                                // --- START OF CHANGES ---

                                // Header Row: Now iterates over indices for stability
                                GridRow {
                                    ForEach(0..<table.headers.count, id: \.self) { index in
                                        Text(table.headers[index])
                                            .font(.headline)
                                            .gridColumnAlignment(.leading)
                                    }
                                }
                                
                                // Divider now correctly spans all columns
                                Divider()
                                    .gridCellColumns(table.headers.count)

                                // Data Rows: Also iterates over indices
                                ForEach(0..<table.rows.count, id: \.self) { rowIndex in
                                    let row = table.rows[rowIndex]
                                    GridRow {
                                        ForEach(0..<row.count, id: \.self) { cellIndex in
                                            Text(row[cellIndex])
                                        }
                                    }
                                }
                                // --- END OF CHANGES ---
                            }
                            .padding(.top, 4)
                        }
                    }
                }
                .padding()
            }

            Divider()

            // Footer (no changes here)
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

    /// Parses the raw multi-line string into an array of table objects.
    private static func parseRawTextToTables(_ text: String) -> [QueryResultTable] {
        let sections = text.components(separatedBy: "--- Query:").dropFirst()
        
        return sections.compactMap { section in
            let lines = section.trimmingCharacters(in: .whitespacesAndNewlines).components(separatedBy: .newlines)
            guard !lines.isEmpty else { return nil }

            let title = "--- Query:" + lines.first!
            let remainingLines = lines.dropFirst()
            
            guard remainingLines.count >= 2 else { return nil }
            
            let headers = remainingLines.first!.components(separatedBy: "|").map { $0.trimmingCharacters(in: .whitespaces) }
            let dataRows = remainingLines.dropFirst().map { rowString in
                rowString.components(separatedBy: "|").map { $0.trimmingCharacters(in: .whitespaces) }
            }
            
            return QueryResultTable(title: title, headers: headers, rows: dataRows)
        }
    }
}


//// MARK: - Preview
//
//#Preview {
//    @MainActor
//    struct PreviewWrapper: View {
//        @StateObject private var viewModel = AdvisorViewModel()
//        @StateObject private var appState = AppState()
//        
//        @State private var showPanelForPreview: Bool = true
//
//        var body: some View {
//            AdvisorView(viewModel: viewModel)
//                .environmentObject(appState)
//                .onAppear {
//                    appState.isDatabaseReady = true
//                    viewModel.isAPIKeySet = true
//                    updatePreviewPanel(on: showPanelForPreview)
//                }
//                .onChange(of: showPanelForPreview) {
//                    updatePreviewPanel(on: $0)
//                }
//                .toolbar {
//                    ToolbarItem {
//                        Toggle("Show Data Panel", isOn: $showPanelForPreview)
//                    }
//                }
//        }
//        
//        private func updatePreviewPanel(on: Bool) {
//            if on {
//                viewModel.retrievedDataForConfirmation = """
//                --- Query: SELECT problemName, onsetDate FROM problems ---
//                problemName | onsetDate
//                Headache | 2025-07-11
//                Fever | 2025-07-11
//
//                --- Query: SELECT medicationName, status FROM medications ---
//                medicationName | status
//                Ibuprofen | active
//                """
//            } else {
//                viewModel.retrievedDataForConfirmation = ""
//            }
//        }
//    }
//    
//    return PreviewWrapper()
//}
