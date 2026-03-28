// Imports the fundamental Swift library for core functionalities.
import Foundation

/// A class that holds the global state of the application, primarily the path to the database.
/// By conforming to `ObservableObject`, it can be used within a SwiftUI environment to automatically
/// update views whenever its `@Published` properties change.
class AppState: ObservableObject {
    
    /// The URL path to the SQLite database file. This property is marked as `@Published`,
    /// so any SwiftUI views observing an instance of `AppState` will automatically re-render when it changes.
    @Published var databasePath: URL? {
        /// A property observer that runs whenever a new value is assigned to `databasePath`.
        didSet {
            // Update the `isDatabaseReady` flag based on whether the path is nil or not.
            isDatabaseReady = databasePath != nil
            // Persist the new URL to `UserDefaults` so it can be reloaded the next time the app launches.
            UserDefaults.standard.set(databasePath, forKey: "databasePath")
        }
    }
    
    /// A boolean flag indicating whether a valid database path has been set.
    /// This provides a simple way for the UI to check if the database-dependent features can be enabled.
    @Published var isDatabaseReady: Bool = false
    
    /// The initializer for the AppState class.
    init() {
        // When the app starts, attempt to retrieve the last saved database URL from UserDefaults.
        if let url = UserDefaults.standard.url(forKey: "databasePath"),
           // Also, verify that a file actually exists at that saved path to prevent using a stale URL.
           FileManager.default.fileExists(atPath: url.path) {
            // If the URL is valid and the file exists, set it as the current database path.
            self.databasePath = url
        }
    }
    
    /// A public method to allow other parts of the app to set the database path.
    /// - Parameter url: The new URL for the database file.
    func setDatabasePath(_ url: URL) {
        // Assigning the URL to the `databasePath` property will trigger its `didSet` observer.
        self.databasePath = url
    }
}
