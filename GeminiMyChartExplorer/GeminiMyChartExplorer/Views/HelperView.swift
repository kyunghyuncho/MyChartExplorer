import SwiftUI

/// A view that displays a single chat message bubble, with styling based on the message's role (user, assistant, or system).
/// It includes logic to parse and render basic Markdown from the message text.
struct MessageView: View {
    /// The `ChatMessage` object containing the role and text for this message.
    let message: ChatMessage
    /// The processed, styled text to be displayed. It's an `AttributedString` to support Markdown.
    private let attributedText: AttributedString

    /// A custom initializer to process the message's text before the view is rendered.
    init(message: ChatMessage) {
        self.message = message
        do {
            // Attempt to convert the message string from Markdown to a styled AttributedString.
            // The options are set to parse only inline styles and preserve whitespace.
            var options = AttributedString.MarkdownParsingOptions()
            options.interpretedSyntax = .inlineOnlyPreservingWhitespace
            self.attributedText = try AttributedString(markdown: message.text, options: options)
        } catch {
            // If Markdown parsing fails (e.g., due to malformed input), fall back to using the plain text.
            // This prevents the app from crashing and ensures the message is still displayed.
            self.attributedText = AttributedString(message.text)
            print("Error parsing markdown: \(error)")
        }
    }

    var body: some View {
        HStack {
            // If the message is from the user, add a spacer to push the bubble to the right.
            if message.role == .user {
                Spacer(minLength: 64)
            }

            // Display the fully-processed attributedText.
            Text(attributedText)
                .font(.system(size: 14))
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
                .background(bubbleColor)
                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                .foregroundStyle(foregroundColor)
                .textSelection(.enabled) // Allow users to select and copy text from the message.

            // If the message is not from the user, add a spacer to push the bubble to the left.
            if message.role != .user {
                Spacer(minLength: 64)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: - Helper Properties for Styling
    
    /// A computed property that determines the background color of the message bubble based on the sender's role.
    private var bubbleColor: Color {
        switch message.role {
        case .user:
            return .blue
        case .assistant:
            return Color(NSColor.controlBackgroundColor) // A standard system background color.
        case .system:
            return .clear // System messages have no background.
        }
    }

    /// A computed property that determines the text color based on the sender's role.
    private var foregroundColor: Color {
        switch message.role {
        case .user:
            return .white
        case .assistant:
            return .primary // Standard text color.
        case .system:
            return .secondary // A lighter color for less important system messages.
        }
    }
}

/// A modal-like view that presents retrieved data to the user and asks for confirmation before proceeding.
struct ConfirmationView: View {
    /// The string of data retrieved from the database to be displayed.
    let retrievedData: String
    /// A closure to be executed when the user confirms.
    let onConfirm: () -> Void
    /// A closure to be executed when the user cancels.
    let onCancel: () -> Void
    
    var body: some View {
        VStack(spacing: 20) {
            Text("Confirm Data Usage")
                .font(.title2).fontWeight(.bold)
            
            Text("The following relevant information was retrieved from your record. Is it okay to send this to the AI for analysis?")
                .multilineTextAlignment(.center)
                .foregroundColor(.secondary)
            
            // A scrollable view to display the retrieved data, which could be lengthy.
            ScrollView {
                Text(retrievedData)
                    .font(.system(.body, design: .monospaced)) // Monospaced font for tabular data.
                    .padding()
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color(NSColor.textBackgroundColor))
                    .cornerRadius(8)
            }
            
            HStack {
                Button("Cancel", role: .cancel, action: onCancel)
                Button("Confirm & Send", action: onConfirm)
                    .keyboardShortcut(.defaultAction) // Allows pressing Enter to confirm.
            }
        }
        .padding()
        .frame(width: 500, height: 400)
    }
}

/// A simple view that attempts to render basic Markdown elements like headers, lists, and bold text.
struct MarkdownTextView: View {
    let markdown: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Split the markdown string into lines and process each one.
            ForEach(markdown.components(separatedBy: "\n"), id: \.self) { line in
                if line.starts(with: "# ") {
                    Text(line.dropFirst(2))
                        .font(.title)
                        .fontWeight(.bold)
                } else if line.starts(with: "## ") {
                    Text(line.dropFirst(3))
                        .font(.title2)
                        .fontWeight(.semibold)
                } else if line.starts(with: "* ") {
                    HStack(alignment: .top) {
                        Text("•")
                        Text(line.dropFirst(2))
                    }
                } else {
                    // For regular lines, process for inline styles like bold.
                    Text(renderInlineMarkdown(String(line)))
                }
            }
        }
    }
    
    /// A helper function to render inline bold markdown (`**text**`).
    private func renderInlineMarkdown(_ line: String) -> AttributedString {
        var attributedString = AttributedString()
        // Split the line by the bold delimiter "**".
        let components = line.components(separatedBy: "**")
        for (index, component) in components.enumerated() {
            var attrComponent = AttributedString(component)
            // Every odd-indexed component is inside the bold delimiters.
            if index % 2 == 1 {
                attrComponent.inlinePresentationIntent = .stronglyEmphasized
            }
            attributedString.append(attrComponent)
        }
        return attributedString
    }
}

/// A generic, reusable view for displaying a placeholder state, such as an error or an empty view.
/// It can optionally include custom content like buttons or input fields.
struct PlaceholderView<Content: View>: View {
    let imageName: String
    let title: String
    let subtitle: String
    /// The custom content to be displayed below the main text.
    let content: Content

    /// An initializer that uses a `@ViewBuilder` to allow for flexible content creation.
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
            
            // Only add the content VStack if the provided content is not an EmptyView.
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
