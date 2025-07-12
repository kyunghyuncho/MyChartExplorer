import SwiftUI

struct ContentView: View {
    @StateObject private var appState = AppState()
    @StateObject private var advisorViewModel = AdvisorViewModel()

    var body: some View {
        TabView {
            AdvisorView(viewModel: advisorViewModel)
                .tabItem {
                    Label("Advisor", systemImage: "bubble.left.and.bubble.right")
                }
                .environmentObject(appState)

            RecordsView()
                .tabItem {
                    Label("Records", systemImage: "list.bullet.clipboard")
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
