import SwiftUI

/// A SwiftUI view that provides the user interface for importing clinical data from XML files into a new SQLite database.
struct ImporterView: View {
    // MARK: - Environment and State
    
    /// Access to the global application state, used to set the database path upon successful import.
    @EnvironmentObject var appState: AppState
    /// The view model that manages the state and logic for the import process.
    @StateObject private var importer = DataImporter()
    /// A focus state variable to control keyboard focus, primarily for keyboard shortcuts.
    @FocusState private var isImporterFocused: Bool

    // MARK: - Body
    
    var body: some View {
        /// A split view that divides the screen into a control panel on the left and a log view on the right.
        HSplitView {
            controlPanelView
                .frame(minWidth: 350, idealWidth: 400, maxWidth: 500)
            
            logView
        }
        .navigationTitle("Data Importer")
        .onAppear { isImporterFocused = true } // Set focus when the view appears.
        // This hidden text field is a workaround to allow the view to receive focus for keyboard shortcuts.
        .overlay(
            TextField("", text: .constant(""))
                .focused($isImporterFocused)
                .opacity(0)
        )
    }

    // MARK: - Subviews

    /// The left panel of the split view, containing all the controls for the import process.
    private var controlPanelView: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("MyChart Importer")
                .font(.largeTitle.bold())
                .padding(.bottom, 10)

            // Step 1: File Selection
            ImporterStepView(step: 1, title: "Select XML Files") {
                fileSelectionView
            }
            
            // Step 2: Database Destination
            ImporterStepView(step: 2, title: "Set Database Location") {
                databaseDestinationView
            }
            
            Spacer() // Pushes the import button to the bottom.
            
            importButtonView
        }
        .padding()
        .background(Color(NSColor.windowBackgroundColor))
    }
    
    /// A view for selecting, displaying, and clearing the list of XML files to be imported.
    private var fileSelectionView: some View {
        VStack {
            ZStack {
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color(NSColor.controlBackgroundColor))

                if importer.xmlFiles.isEmpty {
                    Text("Click 'Add Files' to begin.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                } else {
                    // A scrollable list to display the names of the selected files.
                    ScrollView {
                        VStack(alignment: .leading, spacing: 2) {
                            ForEach(importer.xmlFiles, id: \.self) { url in
                                Text(url.lastPathComponent)
                                    .font(.callout)
                                    .lineLimit(1)
                                    .truncationMode(.middle) // Truncate long file names in the middle.
                                    .padding(.vertical, 2)
                            }
                        }
                        .padding(10)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            }
            .frame(height: 150)

            HStack {
                Button("Add Files", systemImage: "plus") { importer.selectFiles() }
                Spacer()
                Button("Clear", systemImage: "trash", role: .destructive) { importer.clearFiles() }
                    .disabled(importer.xmlFiles.isEmpty)
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        }
    }

    /// A view for setting the destination file path for the new database.
    private var databaseDestinationView: some View {
        HStack {
            Image(systemName: "folder.badge.plus")
                .font(.title2)
                .foregroundStyle(.secondary)
                .frame(width: 30)

            VStack(alignment: .leading) {
                Text(importer.databaseURL?.lastPathComponent ?? "No file set")
                    .font(.headline)
                Text(importer.databaseURL != nil ? (importer.databaseURL!.deletingLastPathComponent().path) : "Select a folder and name for the database")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            
            Spacer()
            
            Button("Set...") { importer.setDatabaseDestination() }
                .buttonStyle(.bordered)
        }
        .padding()
        .background(Color(NSColor.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
    
    /// A view that conditionally displays either the "Start Import" button or a progress indicator.
    @ViewBuilder
    private var importButtonView: some View {
        if importer.isImporting {
            // Show a progress indicator while the import is in progress.
            HStack(spacing: 10) {
                ProgressView()
                    .scaleEffect(0.8)
                Text("Importing... Please Wait")
                    .font(.headline)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 8)
        } else {
            // Show the "Start Import" button.
            Button {
                importer.startImport { successURL in
                    // When the import completes, this closure is called.
                    // If successful, it sets the new database path in the global app state.
                    if let url = successURL {
                        appState.setDatabasePath(url)
                    }
                }
            } label: {
                HStack {
                    Image(systemName: "play.fill")
                    Text("Start Import")
                }
                .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .disabled(!importer.canStartImport)
            // Allows using the Enter key to start the import when this view has focus.
            .keyboardShortcut(.return, modifiers: isImporterFocused ? [] : [.command, .shift])
        }
    }

    /// The right panel of the split view, which displays a running log of the import process.
    private var logView: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("Import Log")
                    .font(.headline)
                Spacer()
                Button("Clear Log") { importer.clearLog() }
                    .buttonStyle(.borderless)
            }
            .padding([.horizontal, .top])
            .padding(.bottom, 8)
            
            Divider()

            // A scroll view that automatically scrolls to the bottom as new log messages are added.
            ScrollViewReader { proxy in
                ScrollView {
                    Text(importer.logOutput)
                        .font(.system(.body, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding()
                        .id("logEnd") // An anchor at the end of the log text.
                }
                .onChange(of: importer.logOutput) { _ in
                    // Whenever the log output changes, scroll to the anchor.
                    withAnimation { proxy.scrollTo("logEnd", anchor: .bottom) }
                }
            }
        }
        .background(.regularMaterial)
    }
}

// MARK: - Subviews

/// A reusable view for creating a numbered step in a process, like the import workflow.
private struct ImporterStepView<Content: View>: View {
    let step: Int
    let title: String
    /// The content of the step, provided via a closure with a ViewBuilder.
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 12) {
                Text("\(step)")
                    .font(.headline)
                    .foregroundStyle(.white)
                    .frame(width: 24, height: 24)
                    .background(Color.accentColor, in: Circle())
                
                Text(title)
                    .font(.title3)
                    .fontWeight(.semibold)
            }
            
            content
                .padding(.leading, 36) // Indent the content to align it under the title.
        }
    }
}

// MARK: - Preview

#Preview {
    ImporterView()
        .environmentObject(AppState())
}
