import SwiftData
import SwiftUI

@main
struct JushenZhiduApp: App {
    @StateObject private var library = LibraryViewModel()
    @StateObject private var settings = AppSettings()

    private let modelContainer: ModelContainer = {
        do {
            return try ModelContainer(
                for: PaperRecord.self,
                CategoryRecord.self,
                KeywordGroupRecord.self,
                KeywordRuleRecord.self,
                ArxivPageCacheRecord.self
            )
        } catch {
            fatalError("Failed to create SwiftData container: \(error)")
        }
    }()

    init() {
        AppTheme.configureAppAppearance()
    }

    var body: some Scene {
        WindowGroup {
            MainTabView()
                .modelContainer(modelContainer)
                .environmentObject(library)
                .environmentObject(settings)
                .tint(AppTheme.ColorToken.warmAction)
        }
    }
}
