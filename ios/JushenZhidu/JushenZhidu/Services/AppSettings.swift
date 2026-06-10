import Combine
import Foundation

@MainActor
final class AppSettings: ObservableObject {
    static let apiKeyAccount = "model-api-key"

    @Published var baseURL: String
    @Published var chatModel: String
    @Published var visionModel: String
    @Published var pdfModel: String
    @Published var temperature: Double
    @Published var maxTokensSingle: Int
    @Published var maxTokensFullText: Int
    @Published var fullTextMaxCharacters: Int
    @Published var fullTextFigureLimit: Int
    @Published var fetchLimit: Int
    @Published var apiKeyDraft: String
    @Published var hasStoredAPIKey: Bool
    @Published var saveMessage: String

    private let defaults: UserDefaults
    private let keychain: KeychainStore

    init(defaults: UserDefaults = .standard, keychain: KeychainStore = KeychainStore()) {
        self.defaults = defaults
        self.keychain = keychain
        self.baseURL = defaults.string(forKey: "settings.baseURL") ?? "https://dashscope.aliyuncs.com/compatible-mode/v1"
        self.chatModel = defaults.string(forKey: "settings.chatModel") ?? "qwen-plus"
        self.visionModel = defaults.string(forKey: "settings.visionModel") ?? "qwen-vl-plus"
        self.pdfModel = defaults.string(forKey: "settings.pdfModel") ?? "qwen-long"
        self.temperature = defaults.object(forKey: "settings.temperature") as? Double ?? 0.2
        self.maxTokensSingle = defaults.object(forKey: "settings.maxTokensSingle") as? Int ?? 1400
        self.maxTokensFullText = defaults.object(forKey: "settings.maxTokensFullText") as? Int ?? 2600
        self.fullTextMaxCharacters = defaults.object(forKey: "settings.fullTextMaxCharacters") as? Int ?? 60_000
        self.fullTextFigureLimit = defaults.object(forKey: "settings.fullTextFigureLimit") as? Int ?? 4
        let storedFetchLimit = defaults.object(forKey: "settings.fetchLimit") as? Int ?? 200
        self.fetchLimit = min(max(storedFetchLimit, 50), 1_000)
        self.apiKeyDraft = ""
        self.hasStoredAPIKey = ((try? keychain.read(account: Self.apiKeyAccount)) ?? "").isEmpty == false
        self.saveMessage = ""
    }

    var normalizedFetchLimit: Int {
        min(max(fetchLimit, 50), 1_000)
    }

    var apiKey: String {
        (try? keychain.read(account: Self.apiKeyAccount)) ?? ""
    }

    var normalizedBaseURL: URL? {
        var raw = baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
        while raw.hasSuffix("/") {
            raw.removeLast()
        }
        return URL(string: raw)
    }

    func save() {
        defaults.set(baseURL, forKey: "settings.baseURL")
        defaults.set(chatModel, forKey: "settings.chatModel")
        defaults.set(visionModel, forKey: "settings.visionModel")
        defaults.set(pdfModel, forKey: "settings.pdfModel")
        defaults.set(temperature, forKey: "settings.temperature")
        defaults.set(maxTokensSingle, forKey: "settings.maxTokensSingle")
        defaults.set(maxTokensFullText, forKey: "settings.maxTokensFullText")
        defaults.set(fullTextMaxCharacters, forKey: "settings.fullTextMaxCharacters")
        defaults.set(fullTextFigureLimit, forKey: "settings.fullTextFigureLimit")
        fetchLimit = normalizedFetchLimit
        defaults.set(fetchLimit, forKey: "settings.fetchLimit")
        if !apiKeyDraft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            do {
                try keychain.save(apiKeyDraft.trimmingCharacters(in: .whitespacesAndNewlines), account: Self.apiKeyAccount)
                apiKeyDraft = ""
                hasStoredAPIKey = true
            } catch {
                saveMessage = "API Key 保存失败：\(error.localizedDescription)"
                return
            }
        }
        saveMessage = "设置已保存"
    }

    func saveFetchLimit() {
        fetchLimit = normalizedFetchLimit
        defaults.set(fetchLimit, forKey: "settings.fetchLimit")
    }

    func clearAPIKey() {
        do {
            try keychain.delete(account: Self.apiKeyAccount)
            hasStoredAPIKey = false
            apiKeyDraft = ""
            saveMessage = "API Key 已清除"
        } catch {
            saveMessage = "API Key 清除失败：\(error.localizedDescription)"
        }
    }
}
