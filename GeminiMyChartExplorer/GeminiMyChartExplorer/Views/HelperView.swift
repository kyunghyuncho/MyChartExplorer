import SwiftUI

/// A view that displays a single chat message bubble.
struct MessageView: View {
    let message: ChatMessage
    private let attributedText: AttributedString

    // 1. We add a custom initializer to process the text.
    init(message: ChatMessage) {
        self.message = message
        do {
            // 2. Try to convert the message string from Markdown to a styled AttributedString.
            var options = AttributedString.MarkdownParsingOptions()
            options.interpretedSyntax = .inlineOnlyPreservingWhitespace
            self.attributedText = try AttributedString(markdown: message.text, options: options)
        } catch {
            // 3. If parsing fails, fall back to the plain text so the app doesn't crash.
            self.attributedText = AttributedString(message.text)
            print("Error parsing markdown: \(error)")
        }
    }

    var body: some View {
        HStack {
            if message.role == .user {
                Spacer(minLength: 64)
            }

            // 4. Use the fully-processed attributedText here.
            Text(attributedText)
                .font(.system(size: 14))
                .padding(.horizontal, 16)
                .padding(.vertical, 12)
                .background(bubbleColor)
                .clipShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
                .foregroundStyle(foregroundColor)

            if message.role != .user {
                Spacer(minLength: 64)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // Helper properties for styling (no changes here)
    private var bubbleColor: Color {
        switch message.role {
        case .user:
            return .blue
        case .assistant:
            return Color(NSColor.controlBackgroundColor)
        case .system:
            return .clear
        }
    }

    private var foregroundColor: Color {
        switch message.role {
        case .user:
            return .white
        case .assistant:
            return .primary
        case .system:
            return .secondary
        }
    }
}

struct ConfirmationView: View {
    let retrievedData: String
    let onConfirm: () -> Void
    let onCancel: () -> Void
    
    var body: some View {
        VStack(spacing: 20) {
            Text("Confirm Data Usage")
                .font(.title2).fontWeight(.bold)
            
            Text("The following relevant information was retrieved from your record. Is it okay to send this to the AI for analysis?")
                .multilineTextAlignment(.center)
                .foregroundColor(.secondary)
            
            ScrollView {
                Text(retrievedData)
                    .font(.system(.body, design: .monospaced))
                    .padding()
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color(NSColor.textBackgroundColor))
                    .cornerRadius(8)
            }
            
            HStack {
                Button("Cancel", role: .cancel, action: onCancel)
                Button("Confirm & Send", action: onConfirm)
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding()
        .frame(width: 500, height: 400)
    }
}

struct MarkdownTextView: View {
    let markdown: String

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
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
                    Text(renderInlineMarkdown(String(line)))
                }
            }
        }
    }
    
    private func renderInlineMarkdown(_ line: String) -> AttributedString {
        var attributedString = AttributedString()
        let components = line.components(separatedBy: "**")
        for (index, component) in components.enumerated() {
            var attrComponent = AttributedString(component)
            if index % 2 == 1 {
                attrComponent.inlinePresentationIntent = .stronglyEmphasized
            }
            attributedString.append(attrComponent)
        }
        return attributedString
    }
}

struct PlaceholderView<Content: View>: View {
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
