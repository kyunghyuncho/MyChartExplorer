import SwiftUI

struct ImporterView: View {
    @EnvironmentObject var appState: AppState
    @StateObject private var importer = DataImporter()
    @FocusState private var isImporterFocused: Bool

    var body: some View {
        HSplitView {
            controlPanelView
                .frame(minWidth: 350, idealWidth: 400, maxWidth: 500)
            
            logView
        }
        .navigationTitle("Data Importer")
        .onAppear { isImporterFocused = true }
        .overlay(
            TextField("", text: .constant(""))
                .focused($isImporterFocused)
                .opacity(0)
        )
    }

    /// The left panel containing all the import controls.
    private var controlPanelView: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("MyChart Importer")
                .font(.largeTitle.bold())
                .padding(.bottom, 10)

            ImporterStepView(step: 1, title: "Select XML Files") {
                fileSelectionView
            }
            
            ImporterStepView(step: 2, title: "Set Database Location") {
                databaseDestinationView
            }
            
            Spacer()
            
            importButtonView
        }
        .padding()
        .background(Color(NSColor.windowBackgroundColor))
    }
    
    /// The view for selecting and clearing XML files.
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
                    ScrollView {
                        VStack(alignment: .leading, spacing: 2) { // Adjust spacing here
                            ForEach(importer.xmlFiles, id: \.self) { url in
                                Text(url.lastPathComponent)
                                    .font(.callout)
                                    .lineLimit(1)
                                    .truncationMode(.middle)
                                    .padding(.vertical, 2) // Reduced vertical padding
                            }
                        }
                        .padding(10)
                        .frame(maxWidth: .infinity, alignment: .leading) // Align frame to the left
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

    /// The view for setting the database file destination.
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
    
    /// The main button to start the import process, which turns into a progress indicator.
    @ViewBuilder
    private var importButtonView: some View {
        if importer.isImporting {
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
            Button {
                importer.startImport { successURL in
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
            .keyboardShortcut(.return, modifiers: isImporterFocused ? [] : [.command, .shift]) // Only active when focused
        }
    }

    /// The right panel that displays the import log.
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

            ScrollViewReader { proxy in
                ScrollView {
                    Text(importer.logOutput)
                        .font(.system(.body, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding()
                        .id("logEnd")
                }
                .onChange(of: importer.logOutput) { _ in
                    withAnimation { proxy.scrollTo("logEnd", anchor: .bottom) }
                }
            }
        }
        .background(.regularMaterial)
    }
}

// MARK: - Subviews

/// A reusable view for creating a numbered step in the import process.
private struct ImporterStepView<Content: View>: View {
    let step: Int
    let title: String
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
                .padding(.leading, 36) // Indent content under the title
        }
    }
}

#Preview {
    ImporterView()
        .environmentObject(AppState())
}
