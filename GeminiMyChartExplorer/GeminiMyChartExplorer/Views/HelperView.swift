import SwiftUI

/// A view that displays a single chat message bubble.
struct MessageView: View {
    let message: ChatMessage

    var body: some View {
        // Changed alignment to .bottom for better multiline support
        HStack(alignment: .bottom, spacing: 10) {
            if message.role == .assistant {
                senderIcon
                messageContent
                Spacer(minLength: 20)
            } else {
                Spacer(minLength: 20)
                messageContent
                senderIcon
            }
        }
    }

    private var senderIcon: some View {
        Image(systemName: message.role == .user ? "person.fill" : "sparkles.fill")
            .font(.system(size: 20))
            .symbolRenderingMode(.multicolor)
            .padding(.bottom, 5)
    }

    @ViewBuilder
    private var messageContent: some View {
        if message.role == .assistant {
            // Define options to parse all supported Markdown syntax.
            let options = AttributedString.MarkdownParsingOptions(
                interpretedSyntax: .inlineOnlyPreservingWhitespace // The correct option is .full
            )

            // Create the attributed string with these options
            let attributedString = try? AttributedString(markdown: message.text, options: options)
            
            Text(attributedString ?? AttributedString(message.text))
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true) // Allow vertical expansion
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(Color(NSColor.controlBackgroundColor))
                .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                .frame(maxWidth: 650, alignment: .leading)
        } else {
            // For user messages, display plain text.
            Text(message.text)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(Color.accentColor)
                .foregroundStyle(.white)
                .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                .frame(maxWidth: 650, alignment: .trailing)
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

