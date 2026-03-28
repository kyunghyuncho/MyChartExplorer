import SwiftUI

/// The main view of the application, which acts as the root container for all other views.
/// It sets up the primary navigation structure using a `TabView`.
struct ContentView: View {
    /// Creates and manages the lifecycle of the `AppState` object.
    /// `@StateObject` ensures that the `appState` is created only once for the lifetime of this view
    /// and is shared with child views via the environment.
    @StateObject private var appState = AppState()
    
    /// Creates and manages the lifecycle of the `AdvisorViewModel`.
    /// This view model is specifically for the `AdvisorView` and is passed down to it.
    @StateObject private var advisorViewModel = AdvisorViewModel()

    var body: some View {
        /// A `TabView` creates a user interface with a tab bar at the bottom (or side, depending on the platform)
        /// for switching between different primary sections of the app.
        TabView {
            // The first tab: The AI Medical Advisor.
            AdvisorView(viewModel: advisorViewModel)
                .tabItem {
                    // The label and icon for the tab.
                    Label("Advisor", systemImage: "bubble.left.and.bubble.right")
                }
                // Injects the shared `appState` into the environment of the AdvisorView and its children.
                .environmentObject(appState)

            // The second tab: The Medical Records Browser.
            RecordsView()
                .tabItem {
                    Label("Records", systemImage: "list.bullet.clipboard")
                }
                // Also injects the shared `appState`.
                .environmentObject(appState)

            // The third tab: The Data Importer.
            ImporterView()
                .tabItem {
                    Label("Importer", systemImage: "square.and.arrow.down.on.square")
                }
                // Also injects the shared `appState`.
                .environmentObject(appState)
        }
        // Sets a minimum size for the application window on macOS.
        .frame(minWidth: 900, minHeight: 700)
    }
}
