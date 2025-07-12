import SwiftUI

struct ContentView: View {
    @StateObject private var appState = AppState()

    var body: some View {
        TabView {
            AdvisorView()
                .tabItem {
                    Label("Advisor", systemImage: "bubble.left.and.bubble.right")
                }
                .environmentObject(appState)

            ImporterView()
                .tabItem {
                    Label("Importer", systemImage: "square.and.arrow.down.on.square")
                }
                .environmentObject(appState)
        }
        .frame(minWidth: 900, minHeight: 700)
    }
}
