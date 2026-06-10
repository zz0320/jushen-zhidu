import Foundation
import SwiftData

@Model
final class PaperRecord: Identifiable {
    @Attribute(.unique) var arxivId: String
    var title: String
    var abstract: String
    var authorsJSON: String
    var affiliationsJSON: String
    var primaryCategory: String
    var categoriesJSON: String
    var publishedAt: Date?
    var updatedAt: Date?
    var absURL: String
    var pdfURL: String
    var doi: String
    var comment: String
    var fetchedForDate: String
    var relevanceScore: Double
    var matchedKeywordsJSON: String
    var topicKey: String
    var isFavorite: Bool
    var translationTitle: String
    var translationContent: String
    var translationModel: String
    var translationGeneratedAt: Date?
    var summaryContent: String
    var summaryModel: String
    var summaryGeneratedAt: Date?
    var fullTextSummaryContent: String
    var fullTextSummaryModel: String
    var fullTextGeneratedAt: Date?
    var fullTextSourceURL: String
    var fullTextSourceChars: Int
    var fullTextUsedChars: Int
    var fullTextTruncated: Bool
    var figurePagesJSON: String
    var createdAt: Date
    var refreshedAt: Date

    var id: String { arxivId }

    init(
        arxivId: String,
        title: String,
        abstract: String,
        authors: [String],
        affiliations: [String],
        primaryCategory: String,
        categories: [String],
        publishedAt: Date?,
        updatedAt: Date?,
        absURL: String,
        pdfURL: String,
        doi: String = "",
        comment: String = "",
        fetchedForDate: String,
        relevanceScore: Double,
        matchedKeywords: [MatchedKeyword],
        topicKey: String
    ) {
        self.arxivId = arxivId
        self.title = title
        self.abstract = abstract
        self.authorsJSON = JSONCoding.encode(authors)
        self.affiliationsJSON = JSONCoding.encode(affiliations)
        self.primaryCategory = primaryCategory
        self.categoriesJSON = JSONCoding.encode(categories)
        self.publishedAt = publishedAt
        self.updatedAt = updatedAt
        self.absURL = absURL
        self.pdfURL = pdfURL
        self.doi = doi
        self.comment = comment
        self.fetchedForDate = fetchedForDate
        self.relevanceScore = relevanceScore
        self.matchedKeywordsJSON = JSONCoding.encode(matchedKeywords)
        self.topicKey = topicKey
        self.isFavorite = false
        self.translationTitle = ""
        self.translationContent = ""
        self.translationModel = ""
        self.translationGeneratedAt = nil
        self.summaryContent = ""
        self.summaryModel = ""
        self.summaryGeneratedAt = nil
        self.fullTextSummaryContent = ""
        self.fullTextSummaryModel = ""
        self.fullTextGeneratedAt = nil
        self.fullTextSourceURL = ""
        self.fullTextSourceChars = 0
        self.fullTextUsedChars = 0
        self.fullTextTruncated = false
        self.figurePagesJSON = "[]"
        self.createdAt = Date()
        self.refreshedAt = Date()
    }

    var authors: [String] { JSONCoding.decode([String].self, from: authorsJSON) ?? [] }
    var affiliations: [String] { JSONCoding.decode([String].self, from: affiliationsJSON) ?? [] }
    var categories: [String] { JSONCoding.decode([String].self, from: categoriesJSON) ?? [] }
    var matchedKeywords: [MatchedKeyword] { JSONCoding.decode([MatchedKeyword].self, from: matchedKeywordsJSON) ?? [] }
    var figurePages: [PaperFigurePage] { JSONCoding.decode([PaperFigurePage].self, from: figurePagesJSON) ?? [] }
    var topic: ResearchTopic { ResearchTopic.byKey(topicKey) }

    var insightCompletionCount: Int {
        [translationContent, summaryContent, fullTextSummaryContent].filter { !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }.count
    }

    var plantTier: PlantTier {
        PlantTier(count: insightCompletionCount)
    }

    var hasFullInsightPack: Bool {
        insightCompletionCount == 3
    }

    func update(from entry: ArxivEntry, fetchedForDate: String, relevanceScore: Double, matchedKeywords: [MatchedKeyword], topicKey: String) {
        title = entry.title
        abstract = entry.abstract
        authorsJSON = JSONCoding.encode(entry.authors)
        affiliationsJSON = JSONCoding.encode(entry.affiliations)
        primaryCategory = entry.primaryCategory
        categoriesJSON = JSONCoding.encode(entry.categories)
        publishedAt = entry.publishedAt
        updatedAt = entry.updatedAt
        absURL = entry.absURL
        pdfURL = entry.pdfURL
        doi = entry.doi
        comment = entry.comment
        self.fetchedForDate = fetchedForDate
        self.relevanceScore = relevanceScore
        matchedKeywordsJSON = JSONCoding.encode(matchedKeywords)
        self.topicKey = topicKey
        refreshedAt = Date()
    }
}

@Model
final class CategoryRecord {
    @Attribute(.unique) var code: String
    var enabled: Bool
    var createdAt: Date

    init(code: String, enabled: Bool = true) {
        self.code = code
        self.enabled = enabled
        self.createdAt = Date()
    }
}

@Model
final class KeywordGroupRecord {
    @Attribute(.unique) var name: String
    var weight: Double
    var enabled: Bool
    var createdAt: Date

    init(name: String, weight: Double, enabled: Bool = true) {
        self.name = name
        self.weight = weight
        self.enabled = enabled
        self.createdAt = Date()
    }
}

@Model
final class KeywordRuleRecord {
    var groupName: String
    var value: String
    var kind: String
    var enabled: Bool
    var createdAt: Date

    init(groupName: String, value: String, kind: KeywordKind = .include, enabled: Bool = true) {
        self.groupName = groupName
        self.value = value
        self.kind = kind.rawValue
        self.enabled = enabled
        self.createdAt = Date()
    }
}

@Model
final class ArxivPageCacheRecord {
    @Attribute(.unique) var cacheKey: String
    var query: String
    var start: Int
    var pageSize: Int
    var responseText: String
    var fetchedAt: Date

    init(cacheKey: String, query: String, start: Int, pageSize: Int, responseText: String) {
        self.cacheKey = cacheKey
        self.query = query
        self.start = start
        self.pageSize = pageSize
        self.responseText = responseText
        self.fetchedAt = Date()
    }
}

enum KeywordKind: String, Codable {
    case include
    case exclude
}

struct MatchedKeyword: Codable, Hashable, Identifiable {
    var id: String { "\(group):\(keyword)" }
    let keyword: String
    let group: String
    let weight: Double
}

struct PaperFigurePage: Codable, Hashable, Identifiable {
    var id: Int { page }
    let page: Int
    let label: String
    let reason: String
}

enum InsightKind: String, CaseIterable, Codable, Identifiable {
    case translation
    case summary
    case fullText

    var id: String { rawValue }

    var label: String {
        switch self {
        case .translation:
            return "译文"
        case .summary:
            return "速读"
        case .fullText:
            return "深读"
        }
    }

    var progressTitle: String {
        switch self {
        case .translation:
            return "生成译文"
        case .summary:
            return "生成速读"
        case .fullText:
            return "生成深读"
        }
    }

    var systemImage: String {
        switch self {
        case .translation:
            return "character.book.closed"
        case .summary:
            return "text.badge.checkmark"
        case .fullText:
            return "doc.richtext"
        }
    }
}

enum PlantTier: String, CaseIterable {
    case sapling
    case young
    case mature
    case ancient

    init(count: Int) {
        switch count {
        case 0: self = .sapling
        default: self = .mature
        }
    }

    var label: String {
        switch self {
        case .sapling:
            return "树苗"
        case .young:
            return "幼树"
        case .mature:
            return "大树"
        case .ancient:
            return "古树"
        }
    }
}

struct ResearchTopic: Identifiable, Hashable {
    let key: String
    let label: String
    let labelZh: String
    let spriteGroups: [String]
    let terrainAssets: [String]
    let include: [String]
    let exclude: [String]

    var id: String { key }

    var assetName: String {
        ForestAssetCatalog.treeAssetName(group: spriteGroups.first ?? "other", variant: nil)
    }

    func spriteAssetName(tier: PlantTier, seed: String) -> String {
        let group = spriteGroups.first ?? "other"
        let variant = fixedSpriteVariant
        if tier == .sapling {
            return ForestAssetCatalog.saplingAssetName(group: group, variant: variant)
        }
        return ForestAssetCatalog.treeAssetName(group: group, variant: variant)
    }

    func terrainAssetName(seed: String) -> String {
        terrainAssets.stablePick(seed: "\(key)-terrain-\(seed)") ?? "ForestTerrainGrass"
    }

    private var fixedSpriteVariant: Int {
        switch key {
        case "foundation":
            return 0
        case "learning_control":
            return 1
        case "navigation_mobility":
            return 2
        case "evaluation_benchmark":
            return 3
        case "perception_spatial":
            return 4
        default:
            return 5
        }
    }

    static let topics: [ResearchTopic] = [
        ResearchTopic(
            key: "foundation",
            label: "Foundation",
            labelZh: "基座模型",
            spriteGroups: ["vla"],
            terrainAssets: ["ForestTerrainMoss", "ForestTerrainWater", "ForestTerrainShade"],
            include: ["vision-language-action", "vision language action", "vla", "vlm", "multimodal", "foundation model", "world model", "generalist robot", "policy optimization"],
            exclude: []
        ),
        ResearchTopic(
            key: "learning_control",
            label: "Learning",
            labelZh: "学习控制",
            spriteGroups: ["robotics"],
            terrainAssets: ["ForestTerrainGrass", "ForestTerrainFlower", "ForestTerrainSprout"],
            include: ["robot learning", "reinforcement learning", "imitation learning", "diffusion policy", "control", "manipulation", "grasp", "dexterous", "trajectory"],
            exclude: ["chatbot", "botnet"]
        ),
        ResearchTopic(
            key: "navigation_mobility",
            label: "Navigation",
            labelZh: "导航移动",
            spriteGroups: ["navigation"],
            terrainAssets: ["ForestTerrainStone", "ForestTerrainFern"],
            include: ["navigation", "objectnav", "vln", "path planning", "locomotion", "slam", "mapping", "mobile robot"],
            exclude: []
        ),
        ResearchTopic(
            key: "evaluation_benchmark",
            label: "Dataset",
            labelZh: "数据评测",
            spriteGroups: ["dataset"],
            terrainAssets: ["ForestTerrainClay", "ForestTerrainAutumn"],
            include: ["dataset", "benchmark", "evaluation", "simulation benchmark", "real2sim", "synthetic data", "data engine"],
            exclude: []
        ),
        ResearchTopic(
            key: "perception_spatial",
            label: "Perception",
            labelZh: "空间感知",
            spriteGroups: ["embodied_ai"],
            terrainAssets: ["ForestTerrainShade", "ForestTerrainFern"],
            include: ["3d perception", "scene understanding", "spatial", "affordance", "pose estimation", "segmentation", "point cloud"],
            exclude: ["disembodied"]
        ),
        ResearchTopic(
            key: "other",
            label: "Other",
            labelZh: "其他",
            spriteGroups: ["other"],
            terrainAssets: ["ForestTerrainGrass", "ForestTerrainClay"],
            include: [],
            exclude: []
        )
    ]

    static var filterTopics: [ResearchTopic] {
        topics.filter { $0.key != "other" } + [byKey("other")]
    }

    static func byKey(_ key: String) -> ResearchTopic {
        topics.first { $0.key == key } ?? topics.last!
    }
}

enum ForestAssetCatalog {
    static func treeAssetName(group: String, variant: Int?) -> String {
        "ForestTree\(assetGroupName(group))\(variant.map(String.init) ?? "")"
    }

    static func saplingAssetName(group: String, variant: Int?) -> String {
        "ForestSapling\(assetGroupName(group))\(variant.map(String.init) ?? "")"
    }

    private static func assetGroupName(_ group: String) -> String {
        switch group {
        case "dataset":
            return "Dataset"
        case "embodied_ai":
            return "EmbodiedAI"
        case "hardware":
            return "Hardware"
        case "manipulation":
            return "Manipulation"
        case "navigation":
            return "Navigation"
        case "robotics":
            return "Robotics"
        case "simulation":
            return "Simulation"
        case "vla":
            return "VLA"
        case "world_model":
            return "WorldModel"
        default:
            return "Other"
        }
    }
}

extension PaperRecord {
    var forestSpriteAssetName: String {
        topic.spriteAssetName(tier: plantTier, seed: arxivId)
    }

    var forestTerrainAssetName: String {
        topic.terrainAssetName(seed: arxivId)
    }

    func hasInsight(_ kind: InsightKind) -> Bool {
        switch kind {
        case .translation:
            return !translationContent.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        case .summary:
            return !summaryContent.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        case .fullText:
            return !fullTextSummaryContent.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }
    }

    var missingInsightKinds: [InsightKind] {
        InsightKind.allCases.filter { !hasInsight($0) }
    }
}

enum TopicClassifier {
    static func classify(title: String, abstract: String, keywords: [MatchedKeyword] = [], categories: [String] = []) -> ResearchTopic {
        let keywordText = keywords.map(\.keyword).joined(separator: " ")
        let categoryText = categories.joined(separator: " ")
        let text = "\(title) \(abstract) \(keywordText) \(categoryText)".lowercased()
        for topic in ResearchTopic.topics where topic.key != "other" {
            if topic.exclude.contains(where: { matches(text, needle: $0) }) {
                continue
            }
            if topic.include.contains(where: { matches(text, needle: $0) }) {
                return topic
            }
        }
        return ResearchTopic.byKey("other")
    }

    private static func matches(_ text: String, needle: String) -> Bool {
        let normalizedNeedle = needle.lowercased()
        if normalizedNeedle.count <= 4, normalizedNeedle.allSatisfy({ $0.isLetter || $0.isNumber }) {
            let pattern = "(?<![a-z0-9])\(NSRegularExpression.escapedPattern(for: normalizedNeedle))(?![a-z0-9])"
            return text.range(of: pattern, options: .regularExpression) != nil
        }
        return text.contains(normalizedNeedle)
    }
}

enum JSONCoding {
    static func encode<T: Encodable>(_ value: T) -> String {
        guard let data = try? JSONEncoder().encode(value) else { return "[]" }
        return String(data: data, encoding: .utf8) ?? "[]"
    }

    static func decode<T: Decodable>(_ type: T.Type, from raw: String) -> T? {
        guard let data = raw.data(using: .utf8) else { return nil }
        return try? JSONDecoder().decode(type, from: data)
    }
}

enum DefaultLibraryConfiguration {
    static let categories = ["cs.RO", "cs.CV", "cs.LG", "cs.AI", "eess.SY"]

    static let keywordGroups: [(name: String, weight: Double, includes: [String], excludes: [String])] = [
        ("Foundation / VLA", 3.8, ["vision-language-action", "vision language action", "vla", "vlm", "world model", "robot foundation model", "generalist robot", "multimodal policy"], []),
        ("Robot Learning", 2.8, ["robot learning", "reinforcement learning", "imitation learning", "diffusion policy", "manipulation", "grasping", "dexterous", "trajectory optimization"], ["chatbot", "web robot"]),
        ("Navigation / Mobility", 2.6, ["navigation", "objectnav", "vln", "slam", "mobile robot", "locomotion", "path planning"], []),
        ("Embodied Data", 2.4, ["dataset", "benchmark", "simulation", "synthetic data", "real robot", "teleoperation", "human demonstration"], []),
        ("Perception / Spatial", 2.2, ["3d perception", "spatial understanding", "affordance", "pose estimation", "segmentation", "point cloud"], [])
    ]
}

enum ArxivBatchCalendar {
    private static let eastern = TimeZone(identifier: "America/New_York")!
    private static let utc = TimeZone(secondsFromGMT: 0)!

    static func isFetchableBatchDay(_ day: Date) -> Bool {
        let weekday = Calendar.gregorian(in: eastern).component(.weekday, from: day)
        return weekday != 6 && weekday != 7
    }

    static func previousFetchableBatchDay(before day: Date) -> Date {
        var candidate = Calendar.gregorian(in: eastern).date(byAdding: .day, value: -1, to: day)!
        while !isFetchableBatchDay(candidate) {
            candidate = Calendar.gregorian(in: eastern).date(byAdding: .day, value: -1, to: candidate)!
        }
        return candidate
    }

    static func nextFetchableBatchDay(after day: Date) -> Date {
        var candidate = Calendar.gregorian(in: eastern).date(byAdding: .day, value: 1, to: day)!
        while !isFetchableBatchDay(candidate) {
            candidate = Calendar.gregorian(in: eastern).date(byAdding: .day, value: 1, to: candidate)!
        }
        return candidate
    }

    static func latestFetchableBatchDay(now: Date = Date()) -> Date {
        let calendar = Calendar.gregorian(in: eastern)
        var candidate = calendar.startOfDay(for: now)
        let hour = calendar.component(.hour, from: now)
        if hour < 20 {
            candidate = calendar.date(byAdding: .day, value: -1, to: candidate)!
        }
        while !isFetchableBatchDay(candidate) {
            candidate = calendar.date(byAdding: .day, value: -1, to: candidate)!
        }
        return candidate
    }

    static func submittedDateQuery(for day: Date) -> String {
        arxivBatchDateRanges(for: day).map { "submittedDate:\($0)" }.joinedForQuery()
    }

    static func arxivBatchDateRanges(for day: Date) -> [String] {
        guard let range = arxivBatchUTCRange(for: day) else { return [] }
        return splitUTCRanges(start: range.start, end: range.end)
    }

    static func arxivBatchUTCRange(for day: Date) -> (start: Date, end: Date)? {
        let calendar = Calendar.gregorian(in: eastern)
        let weekday = calendar.component(.weekday, from: day)
        if weekday == 6 || weekday == 7 {
            return nil
        }
        let startOffset: Int
        let endOffset: Int
        if weekday == 1 {
            startOffset = -3
            endOffset = -2
        } else {
            startOffset = weekday == 2 ? -3 : -1
            endOffset = 0
        }
        let startDay = calendar.date(byAdding: .day, value: startOffset, to: day)!
        let endDay = calendar.date(byAdding: .day, value: endOffset, to: day)!
        var startComponents = calendar.dateComponents([.year, .month, .day], from: startDay)
        startComponents.hour = 14
        startComponents.minute = 0
        var endComponents = calendar.dateComponents([.year, .month, .day], from: endDay)
        endComponents.hour = 13
        endComponents.minute = 59
        guard let start = calendar.date(from: startComponents), let end = calendar.date(from: endComponents) else {
            return nil
        }
        return (start, end)
    }

    static func dayString(_ day: Date) -> String {
        let formatter = DateFormatter()
        formatter.calendar = Calendar.gregorian(in: eastern)
        formatter.timeZone = eastern
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: day)
    }

    static func parseDay(_ value: String) -> Date? {
        let formatter = DateFormatter()
        formatter.calendar = Calendar.gregorian(in: eastern)
        formatter.timeZone = eastern
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.date(from: value)
    }

    private static func splitUTCRanges(start: Date, end: Date) -> [String] {
        let calendar = Calendar.gregorian(in: utc)
        var ranges: [String] = []
        var currentStart = start
        while !calendar.isDate(currentStart, inSameDayAs: end) {
            var endComponents = calendar.dateComponents([.year, .month, .day], from: currentStart)
            endComponents.hour = 23
            endComponents.minute = 59
            let currentEnd = calendar.date(from: endComponents)!
            ranges.append("[\(formatUTC(currentStart)) TO \(formatUTC(currentEnd))]")
            currentStart = calendar.date(byAdding: .minute, value: 1, to: currentEnd)!
        }
        ranges.append("[\(formatUTC(currentStart)) TO \(formatUTC(end))]")
        return ranges
    }

    private static func formatUTC(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.calendar = Calendar.gregorian(in: utc)
        formatter.timeZone = utc
        formatter.dateFormat = "yyyyMMddHHmm"
        return formatter.string(from: date)
    }
}

extension Calendar {
    static func gregorian(in timeZone: TimeZone) -> Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = timeZone
        return calendar
    }
}

private extension Array where Element == String {
    func joinedForQuery() -> String {
        switch count {
        case 0: ""
        case 1: first ?? ""
        default: "(\(joined(separator: " OR ")))"
        }
    }

    func stablePick(seed: String) -> String? {
        guard !isEmpty else { return nil }
        return self[Int(seed.stableForestHash % UInt64(count))]
    }
}

private extension String {
    var stableForestHash: UInt64 {
        var hash: UInt64 = 14_695_981_039_346_656_037
        for byte in utf8 {
            hash ^= UInt64(byte)
            hash &*= 1_099_511_628_211
        }
        return hash
    }
}
