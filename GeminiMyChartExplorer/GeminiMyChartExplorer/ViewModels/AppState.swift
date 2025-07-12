import Foundation

class AppState: ObservableObject {
    @Published var databasePath: URL? {
        didSet {
            isDatabaseReady = databasePath != nil
            UserDefaults.standard.set(databasePath, forKey: "databasePath")
        }
    }
    @Published var isDatabaseReady: Bool = false
    
    init() {
        if let url = UserDefaults.standard.url(forKey: "databasePath"),
           FileManager.default.fileExists(atPath: url.path) {
            self.databasePath = url
        }
    }
    
    func setDatabasePath(_ url: URL) {
        self.databasePath = url
    }
}
