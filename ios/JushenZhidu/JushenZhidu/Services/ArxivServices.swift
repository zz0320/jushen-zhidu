import CryptoKit
import Foundation
import SwiftData

struct ArxivEntry: Hashable {
    let arxivId: String
    let title: String
    let abstract: String
    let authors: [String]
    let affiliations: [String]
    let primaryCategory: String
    let categories: [String]
    let publishedAt: Date?
    let updatedAt: Date?
    let absURL: String
    let pdfURL: String
    let doi: String
    let comment: String
}

struct ArxivFeedPage {
    let entries: [ArxivEntry]
    let totalResults: Int?
}

struct FetchProgress: Equatable {
    var stage: String
    var message: String
    var percent: Double
    var fetched: Int
    var matched: Int
    var saved: Int
    var cachedPages: Int
    var networkRequests: Int
}

struct FetchSummary: Equatable {
    let fetched: Int
    let matched: Int
    let saved: Int
    let updated: Int
    let cachedPages: Int
    let networkRequests: Int
}

enum ArxivServiceError: LocalizedError {
    case noCategories
    case invalidURL
    case invalidResponse

    var errorDescription: String? {
        switch self {
        case .noCategories:
            return "至少需要启用一个 arXiv 分类。"
        case .invalidURL:
            return "无法构造 arXiv 请求地址。"
        case .invalidResponse:
            return "arXiv 返回内容无法解析。"
        }
    }
}

final class ArxivAtomParser: NSObject, XMLParserDelegate {
    private var entries: [ArxivEntry] = []
    private var totalResults: Int?
    private var currentEntry: MutableEntry?
    private var currentText = ""
    private var insideAuthor = false
    private var currentAuthorName = ""

    func parse(_ data: Data) throws -> ArxivFeedPage {
        entries = []
        totalResults = nil
        currentEntry = nil
        let parser = XMLParser(data: data)
        parser.delegate = self
        parser.shouldProcessNamespaces = false
        guard parser.parse() else {
            throw parser.parserError ?? ArxivServiceError.invalidResponse
        }
        return ArxivFeedPage(entries: entries, totalResults: totalResults)
    }

    func parser(_ parser: XMLParser, didStartElement elementName: String, namespaceURI: String?, qualifiedName qName: String?, attributes attributeDict: [String: String] = [:]) {
        let name = normalized(elementName)
        currentText = ""
        if name == "entry" {
            currentEntry = MutableEntry()
        } else if name == "author" {
            insideAuthor = true
            currentAuthorName = ""
        } else if name == "category", let term = attributeDict["term"], currentEntry != nil {
            currentEntry?.categories.append(term)
        } else if name == "primary_category", let term = attributeDict["term"] {
            currentEntry?.primaryCategory = term
        } else if name == "link", currentEntry != nil {
            let href = attributeDict["href"] ?? ""
            let rel = attributeDict["rel"] ?? ""
            let title = attributeDict["title"] ?? ""
            let contentType = attributeDict["type"] ?? ""
            if rel == "alternate", !href.isEmpty {
                currentEntry?.absURL = href
            }
            if title == "pdf" || contentType == "application/pdf" {
                currentEntry?.pdfURL = href
            }
        }
    }

    func parser(_ parser: XMLParser, foundCharacters string: String) {
        currentText += string
    }

    func parser(_ parser: XMLParser, didEndElement elementName: String, namespaceURI: String?, qualifiedName qName: String?) {
        let name = normalized(elementName)
        let text = currentText.normalizedWhitespace
        if name == "entry" {
            if let entry = currentEntry?.build() {
                entries.append(entry)
            }
            currentEntry = nil
        } else if name == "author" {
            if !currentAuthorName.isEmpty {
                currentEntry?.authors.append(currentAuthorName)
            }
            insideAuthor = false
            currentAuthorName = ""
        } else if currentEntry != nil {
            switch name {
            case "id":
                currentEntry?.rawId = text
            case "title":
                currentEntry?.title = text
            case "summary":
                currentEntry?.abstract = text
            case "published":
                currentEntry?.publishedAt = ISO8601DateFormatter.arxiv.date(from: text)
            case "updated":
                currentEntry?.updatedAt = ISO8601DateFormatter.arxiv.date(from: text)
            case "doi":
                currentEntry?.doi = text
            case "comment":
                currentEntry?.comment = text
            case "name" where insideAuthor:
                currentAuthorName = text
            case "affiliation" where insideAuthor:
                if !text.isEmpty, currentEntry?.affiliations.contains(text) == false {
                    currentEntry?.affiliations.append(text)
                }
            default:
                break
            }
        } else if name == "totalResults" {
            totalResults = Int(text)
        }
        currentText = ""
    }

    private func normalized(_ value: String) -> String {
        value.split(separator: ":").last.map(String.init) ?? value
    }

    private struct MutableEntry {
        var rawId = ""
        var title = ""
        var abstract = ""
        var authors: [String] = []
        var affiliations: [String] = []
        var primaryCategory = ""
        var categories: [String] = []
        var publishedAt: Date?
        var updatedAt: Date?
        var absURL = ""
        var pdfURL = ""
        var doi = ""
        var comment = ""

        func build() -> ArxivEntry? {
            let normalizedId = ArxivAtomParser.normalizeArxivId(rawId)
            guard !normalizedId.isEmpty else { return nil }
            return ArxivEntry(
                arxivId: normalizedId,
                title: title,
                abstract: abstract,
                authors: authors,
                affiliations: affiliations.uniqued(),
                primaryCategory: primaryCategory.isEmpty ? (categories.first ?? "") : primaryCategory,
                categories: categories.uniqued(),
                publishedAt: publishedAt,
                updatedAt: updatedAt,
                absURL: absURL.isEmpty ? rawId : absURL,
                pdfURL: pdfURL,
                doi: doi,
                comment: comment
            )
        }
    }

    static func normalizeArxivId(_ raw: String) -> String {
        var value = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        while value.hasSuffix("/") {
            value.removeLast()
        }
        if let range = value.range(of: "/abs/") {
            value = String(value[range.upperBound...])
        }
        return value
    }
}

struct KeywordRuleInput {
    let group: String
    let value: String
    let kind: KeywordKind
    let weight: Double
}

enum ScoringEngine {
    static func score(title: String, abstract: String, rules: [KeywordRuleInput]) -> (score: Double, matched: [MatchedKeyword], excluded: Bool) {
        let text = "\(title) \(abstract)".lowercased()
        var score = 0.0
        var matched: [MatchedKeyword] = []
        for rule in rules {
            guard matches(text, needle: rule.value) else { continue }
            if rule.kind == .exclude {
                return (0, [], true)
            }
            let keyword = MatchedKeyword(keyword: rule.value, group: rule.group, weight: rule.weight)
            if !matched.contains(keyword) {
                matched.append(keyword)
                score += max(0.1, rule.weight)
            }
        }
        return (score, matched, false)
    }

    private static func matches(_ text: String, needle: String) -> Bool {
        let normalized = needle.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !normalized.isEmpty else { return false }
        if normalized.count <= 4, normalized.allSatisfy({ $0.isLetter || $0.isNumber }) {
            let pattern = "(?<![a-z0-9])\(NSRegularExpression.escapedPattern(for: normalized))(?![a-z0-9])"
            return text.range(of: pattern, options: .regularExpression) != nil
        }
        return text.contains(normalized)
    }
}

@MainActor
struct ArxivService {
    var baseURL = URL(string: "https://export.arxiv.org/api/query")!
    var pageSize = 100
    var maxResults = 200
    var cacheEnabled = true
    var requestDelaySeconds: UInt64 = 3

    func fetchPapers(
        for day: Date,
        context: ModelContext,
        forceRefresh: Bool = false,
        progress: @escaping (FetchProgress) -> Void
    ) async throws -> FetchSummary {
        let dayText = ArxivBatchCalendar.dayString(day)
        let categories = try enabledCategories(context: context)
        guard !categories.isEmpty else { throw ArxivServiceError.noCategories }
        let rules = try keywordRules(context: context)
        let query = try buildSearchQuery(categories: categories, day: day)
        var fetched = 0
        var matched = 0
        var saved = 0
        var updated = 0
        var cachedPages = 0
        var networkRequests = 0
        let totalPages = max(1, Int(ceil(Double(maxResults) / Double(pageSize))))
        let parser = ArxivAtomParser()

        for page in 0..<totalPages {
            let start = page * pageSize
            let requestPageSize = min(pageSize, maxResults - start)
            guard requestPageSize > 0 else { break }
            progress(FetchProgress(stage: "requesting", message: "读取 arXiv 第 \(page + 1) 页", percent: Double(page) / Double(totalPages) * 0.72, fetched: fetched, matched: matched, saved: saved, cachedPages: cachedPages, networkRequests: networkRequests))
            let xmlText: String
            if let cached = try cachedPage(query: query, start: start, pageSize: requestPageSize, context: context, forceRefresh: forceRefresh) {
                cachedPages += 1
                xmlText = cached.responseText
            } else {
                if networkRequests > 0 {
                    progress(FetchProgress(stage: "waiting", message: "遵守 arXiv 官方节奏，等待 \(requestDelaySeconds) 秒", percent: Double(page) / Double(totalPages) * 0.72, fetched: fetched, matched: matched, saved: saved, cachedPages: cachedPages, networkRequests: networkRequests))
                    try await Task.sleep(nanoseconds: requestDelaySeconds * 1_000_000_000)
                }
                let data = try await requestPage(query: query, start: start, pageSize: requestPageSize)
                xmlText = String(data: data, encoding: .utf8) ?? ""
                try storeCache(query: query, start: start, pageSize: requestPageSize, responseText: xmlText, context: context)
                networkRequests += 1
            }

            let feed = try parser.parse(Data(xmlText.utf8))
            fetched += feed.entries.count
            for entry in feed.entries {
                let scoreResult = ScoringEngine.score(title: entry.title, abstract: entry.abstract, rules: rules)
                if scoreResult.excluded || scoreResult.score <= 0 {
                    continue
                }
                matched += 1
                let topic = TopicClassifier.classify(title: entry.title, abstract: entry.abstract, keywords: scoreResult.matched, categories: entry.categories)
                if let existing = try existingPaper(arxivId: entry.arxivId, context: context) {
                    existing.update(from: entry, fetchedForDate: dayText, relevanceScore: scoreResult.score, matchedKeywords: scoreResult.matched, topicKey: topic.key)
                    updated += 1
                } else {
                    let paper = PaperRecord(
                        arxivId: entry.arxivId,
                        title: entry.title,
                        abstract: entry.abstract,
                        authors: entry.authors,
                        affiliations: entry.affiliations,
                        primaryCategory: entry.primaryCategory,
                        categories: entry.categories,
                        publishedAt: entry.publishedAt,
                        updatedAt: entry.updatedAt,
                        absURL: entry.absURL,
                        pdfURL: entry.pdfURL,
                        doi: entry.doi,
                        comment: entry.comment,
                        fetchedForDate: dayText,
                        relevanceScore: scoreResult.score,
                        matchedKeywords: scoreResult.matched,
                        topicKey: topic.key
                    )
                    context.insert(paper)
                    saved += 1
                }
            }
            try context.save()
            if feed.entries.count < requestPageSize || (feed.totalResults.map { start + feed.entries.count >= min($0, maxResults) } ?? false) {
                break
            }
        }
        progress(FetchProgress(stage: "complete", message: "抓取完成", percent: 1, fetched: fetched, matched: matched, saved: saved, cachedPages: cachedPages, networkRequests: networkRequests))
        return FetchSummary(fetched: fetched, matched: matched, saved: saved, updated: updated, cachedPages: cachedPages, networkRequests: networkRequests)
    }

    func buildSearchQuery(categories: [String], day: Date) throws -> String {
        guard !categories.isEmpty else { throw ArxivServiceError.noCategories }
        let categoryQuery = "(" + categories.map { "cat:\($0)" }.joined(separator: " OR ") + ")"
        let dateQuery = ArxivBatchCalendar.submittedDateQuery(for: day)
        return "\(categoryQuery) AND \(dateQuery)"
    }

    private func requestPage(query: String, start: Int, pageSize: Int) async throws -> Data {
        var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)
        components?.queryItems = [
            URLQueryItem(name: "search_query", value: query),
            URLQueryItem(name: "start", value: String(start)),
            URLQueryItem(name: "max_results", value: String(pageSize)),
            URLQueryItem(name: "sortBy", value: "submittedDate"),
            URLQueryItem(name: "sortOrder", value: "descending")
        ]
        guard let url = components?.url else { throw ArxivServiceError.invalidURL }
        var request = URLRequest(url: url)
        request.setValue("jushen-zhidu-ios/0.1 (arXiv API client)", forHTTPHeaderField: "User-Agent")
        request.timeoutInterval = 30
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, 200..<300 ~= http.statusCode else {
            throw ArxivServiceError.invalidResponse
        }
        return data
    }

    private func enabledCategories(context: ModelContext) throws -> [String] {
        let rows = try context.fetch(FetchDescriptor<CategoryRecord>())
        let enabled = rows.filter(\.enabled).map(\.code)
        return enabled.isEmpty ? DefaultLibraryConfiguration.categories : enabled
    }

    private func keywordRules(context: ModelContext) throws -> [KeywordRuleInput] {
        let groups = try context.fetch(FetchDescriptor<KeywordGroupRecord>())
        let rules = try context.fetch(FetchDescriptor<KeywordRuleRecord>())
        let weights = Dictionary(uniqueKeysWithValues: groups.map { ($0.name, $0.enabled ? $0.weight : 0) })
        return rules.compactMap { rule in
            guard rule.enabled, let weight = weights[rule.groupName], weight > 0 else { return nil }
            return KeywordRuleInput(group: rule.groupName, value: rule.value, kind: KeywordKind(rawValue: rule.kind) ?? .include, weight: weight)
        }
    }

    private func existingPaper(arxivId: String, context: ModelContext) throws -> PaperRecord? {
        try context.fetch(FetchDescriptor<PaperRecord>()).first { $0.arxivId == arxivId }
    }

    private func cachedPage(query: String, start: Int, pageSize: Int, context: ModelContext, forceRefresh: Bool) throws -> ArxivPageCacheRecord? {
        guard cacheEnabled, !forceRefresh else { return nil }
        let key = cacheKey(query: query, start: start, pageSize: pageSize)
        return try context.fetch(FetchDescriptor<ArxivPageCacheRecord>()).first { $0.cacheKey == key }
    }

    private func storeCache(query: String, start: Int, pageSize: Int, responseText: String, context: ModelContext) throws {
        guard cacheEnabled else { return }
        let key = cacheKey(query: query, start: start, pageSize: pageSize)
        if let existing = try context.fetch(FetchDescriptor<ArxivPageCacheRecord>()).first(where: { $0.cacheKey == key }) {
            existing.responseText = responseText
            existing.fetchedAt = Date()
            existing.pageSize = pageSize
        } else {
            context.insert(ArxivPageCacheRecord(cacheKey: key, query: query, start: start, pageSize: pageSize, responseText: responseText))
        }
    }

    private func cacheKey(query: String, start: Int, pageSize: Int) -> String {
        let raw = "\(baseURL.absoluteString)|\(query)|\(start)|\(pageSize)"
        let digest = SHA256.hash(data: Data(raw.utf8))
        return digest.map { String(format: "%02x", $0) }.joined()
    }
}

private extension ISO8601DateFormatter {
    static let arxiv: ISO8601DateFormatter = {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter
    }()
}

private extension String {
    var normalizedWhitespace: String {
        components(separatedBy: .whitespacesAndNewlines).filter { !$0.isEmpty }.joined(separator: " ")
    }
}

private extension Array where Element: Hashable {
    func uniqued() -> [Element] {
        var seen = Set<Element>()
        return filter { seen.insert($0).inserted }
    }
}
