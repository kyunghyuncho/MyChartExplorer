import SwiftUI

struct AdvisorView: View {
    @EnvironmentObject var appState: AppState
    @StateObject private var viewModel = AdvisorViewModel()
    @State private var userMessage: String = ""
    @State private var apiKeyInput: String = ""
    @FocusState private var isAdvisorFocused: Bool

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
                chatInterface
            }
        }
        .navigationTitle("Medical Advisor")
        .onAppear {
            viewModel.setup(appState: appState)
            isAdvisorFocused = true
        }
        .sheet(isPresented: $viewModel.isShowingConfirmation) {
            ConfirmationView(
            retrievedData: viewModel.retrievedDataForConfirmation,
                onConfirm: {
                    viewModel.isShowingConfirmation = false
                    viewModel.getFinalAdvice()
                },
             onCancel: {
                 viewModel.isShowingConfirmation = false
                 viewModel.cancelAdvice()
             }
            )
        }
        .overlay(
            TextField("", text: .constant(""))
                .focused($isAdvisorFocused)
                .opacity(0)
        )
    }

    /// A view for entering the API key.
    private var apiKeyEntryView: some View {
        PlaceholderView(
            imageName: "key.shield",
            title: "Gemini API Key Required",
            subtitle: "Please enter your API key to use the Advisor. It will be stored securely in your Keychain."
        ) {
            // Custom content for the input field and button
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
            // Chat History
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(spacing: 20) {
                        ForEach(viewModel.conversation) { msg in
                            MessageView(message: msg)
                        }
                    }
                    .padding()
                    .id("bottom") // ID for scrolling
                }
                .background(Color(NSColor.windowBackgroundColor))
                .onChange(of: viewModel.conversation.count) { _ in
                    withAnimation {
                        proxy.scrollTo("bottom", anchor: .bottom)
                    }
                }
            }
            
            // Divider and Input Bar
            Divider()
            chatInputBar
        }
        .ignoresSafeArea(.keyboard, edges: .bottom)
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
                .onSubmit {
                    sendMessage()
                }
            
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

/// A reusable view for empty or setup states.
private struct PlaceholderView<Content: View>: View {
    let imageName: String
    let title: String
    let subtitle: String
    let content: Content

    init(imageName: String, title: String, subtitle: String, @ViewBuilder content: () -> Content = { EmptyView() }) {
        self.imageName = imageName
        self.title = title
        self.subtitle = subtitle
        self.content = content()
    }

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: imageName)
                .font(.system(size: 50, weight: .light))
                .foregroundStyle(.secondary)
                .padding(.bottom, 10)
            
            Text(title)
                .font(.title2)
                .fontWeight(.semibold)
            
            Text(subtitle)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 400)
            
            if !(content is EmptyView) {
                VStack {
                    content
                }
                .padding(.top)
            }
        }
        .padding()
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color(NSColor.windowBackgroundColor))
    }
}


#Preview {
    // This preview helps visualize the layout.
    // You'll need to create mock data to see it fully.
    struct PreviewWrapper: View {
        @StateObject private var appState = AppState()
        
        var body: some View {
            AdvisorView()
                .environmentObject(appState)
                .onAppear {
                    // Set this to true to preview the chat interface
                     appState.isDatabaseReady = true
                }
        }
    }
    return PreviewWrapper()
}
