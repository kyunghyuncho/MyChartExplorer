import SwiftUI

/// The `@main` attribute identifies this struct as the entry point for the application.
/// When the app launches, the system creates an instance of this struct and calls its `body` property.
@main
struct GeminiMyChartExplorerApp: App {
    /// The `body` of an `App` defines the scenes that make up the application.
    var body: some Scene {
        /// A `WindowGroup` is a scene that manages one or more windows for the app.
        /// On macOS, this will create a new window when the app launches.
        WindowGroup {
            /// `ContentView` is the root view of the application's user interface.
            ContentView()
        }
        // These modifiers are specific to macOS and control the appearance of the app's window.
        .windowStyle(DefaultWindowStyle()) // Uses the standard window appearance for the platform.
        .windowToolbarStyle(UnifiedWindowToolbarStyle()) // Integrates the toolbar area with the title bar for a modern look.
    }
}
