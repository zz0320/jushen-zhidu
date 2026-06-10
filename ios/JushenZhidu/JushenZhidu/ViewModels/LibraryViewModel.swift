import Combine
import Foundation
import SwiftData

@MainActor
final class LibraryViewModel: ObservableObject {
    @Published var selectedBatchDay: Date = ArxivBatchCalendar.latestFetchableBatchDay()
    @Published var searchText = ""
    @Published var selectedTopicKey = "all"
    @Published var showingFavoritesOnly = false
    @Published var activeTask: TaskActivity?
    @Published var lastMessage = ""
    @Published var lastError = ""
    @Published var pdfCacheBytes: Int64 = PaperPDFCache.totalSize()

    var selectedBatchDayText: String {
        ArxivBatchCalendar.dayString(selectedBatchDay)
    }

    func seedDefaultsIfNeeded(context: ModelContext) {
        do {
            let categories = try context.fetch(FetchDescriptor<CategoryRecord>())
            if categories.isEmpty {
                for code in DefaultLibraryConfiguration.categories {
                    context.insert(CategoryRecord(code: code))
                }
            }
            let groups = try context.fetch(FetchDescriptor<KeywordGroupRecord>())
            if groups.isEmpty {
                for group in DefaultLibraryConfiguration.keywordGroups {
                    context.insert(KeywordGroupRecord(name: group.name, weight: group.weight))
                    for value in group.includes {
                        context.insert(KeywordRuleRecord(groupName: group.name, value: value, kind: .include))
                    }
                    for value in group.excludes {
                        context.insert(KeywordRuleRecord(groupName: group.name, value: value, kind: .exclude))
                    }
                }
            }
            try context.save()
        } catch {
            lastError = error.localizedDescription
        }
    }

    func previousBatchDay() {
        selectedBatchDay = ArxivBatchCalendar.previousFetchableBatchDay(before: selectedBatchDay)
    }

    func nextBatchDay() {
        let next = ArxivBatchCalendar.nextFetchableBatchDay(after: selectedBatchDay)
        if next <= ArxivBatchCalendar.latestFetchableBatchDay() {
            selectedBatchDay = next
        }
    }

    func fetchCurrentBatch(context: ModelContext, forceRefresh: Bool = false, settings: AppSettings) {
        activeTask = TaskActivity(title: "同步 arXiv", stage: "queued", message: "准备抓取论文", percent: 0.02)
        lastError = ""
        Task {
            do {
                let summary = try await ArxivService(maxResults: settings.normalizedFetchLimit).fetchPapers(for: selectedBatchDay, context: context, forceRefresh: forceRefresh) { [weak self] progress in
                    self?.activeTask = TaskActivity(title: "同步 arXiv", stage: progress.stage, message: progress.message, percent: progress.percent)
                }
                lastMessage = "读取 \(summary.fetched) 篇，命中 \(summary.matched) 篇，新增 \(summary.saved) 篇，刷新 \(summary.updated) 篇。"
                activeTask = TaskActivity(title: "同步 arXiv", stage: "complete", message: lastMessage, percent: 1)
                try context.save()
            } catch {
                lastError = error.localizedDescription
                activeTask = TaskActivity(title: "同步 arXiv", stage: "failed", message: lastError, percent: 1)
            }
        }
    }

    func generateInsights(for paper: PaperRecord, context: ModelContext, settings: AppSettings) {
        runInsightGeneration(
            kinds: InsightKind.allCases,
            title: "刷新阅读包",
            successMessage: "已刷新 \(paper.title) 的智能阅读包。",
            for: paper,
            context: context,
            settings: settings
        )
    }

    func generateTranslation(for paper: PaperRecord, context: ModelContext, settings: AppSettings) {
        runInsightGeneration(
            kinds: [.translation],
            title: InsightKind.translation.progressTitle,
            successMessage: "已生成 \(paper.title) 的译文。",
            for: paper,
            context: context,
            settings: settings
        )
    }

    func generateSummary(for paper: PaperRecord, context: ModelContext, settings: AppSettings) {
        runInsightGeneration(
            kinds: [.summary],
            title: InsightKind.summary.progressTitle,
            successMessage: "已生成 \(paper.title) 的速读总结。",
            for: paper,
            context: context,
            settings: settings
        )
    }

    func generateFullText(for paper: PaperRecord, context: ModelContext, settings: AppSettings) {
        runInsightGeneration(
            kinds: [.fullText],
            title: InsightKind.fullText.progressTitle,
            successMessage: "已生成 \(paper.title) 的深读总结。",
            for: paper,
            context: context,
            settings: settings
        )
    }

    func completeMissingInsights(for paper: PaperRecord, context: ModelContext, settings: AppSettings) {
        let missing = paper.missingInsightKinds
        runInsightGeneration(
            kinds: missing.isEmpty ? InsightKind.allCases : missing,
            title: missing.isEmpty ? "刷新阅读包" : "补全缺失",
            successMessage: missing.isEmpty ? "已刷新 \(paper.title) 的智能阅读包。" : "已补全 \(paper.title) 的缺失内容。",
            for: paper,
            context: context,
            settings: settings
        )
    }

    func cachedPDF(for paper: PaperRecord) -> CachedPaperPDF? {
        PaperPDFCache.cachedPDF(for: paper)
    }

    func preparePDF(for paper: PaperRecord) async throws -> CachedPaperPDF {
        activeTask = TaskActivity(title: "缓存 PDF", stage: "download", message: "正在准备论文 PDF", percent: 0.18)
        do {
            let cached = try await PaperPDFCache.storePDF(for: paper)
            pdfCacheBytes = PaperPDFCache.totalSize()
            activeTask = TaskActivity(title: "缓存 PDF", stage: "complete", message: "PDF 已可离线阅读", percent: 1)
            return cached
        } catch {
            lastError = error.localizedDescription
            activeTask = TaskActivity(title: "缓存 PDF", stage: "failed", message: lastError, percent: 1)
            throw error
        }
    }

    func toggleFavorite(_ paper: PaperRecord, context: ModelContext) {
        paper.isFavorite.toggle()
        do {
            try context.save()
        } catch {
            lastError = error.localizedDescription
        }
    }

    func clearPapers(context: ModelContext) {
        do {
            for paper in try context.fetch(FetchDescriptor<PaperRecord>()) {
                context.delete(paper)
            }
            for cache in try context.fetch(FetchDescriptor<ArxivPageCacheRecord>()) {
                context.delete(cache)
            }
            try PaperPDFCache.removeAll()
            pdfCacheBytes = 0
            try context.save()
            lastMessage = "论文和页面缓存已清理。"
        } catch {
            lastError = error.localizedDescription
        }
    }

    func clearPDFCache() {
        do {
            try PaperPDFCache.removeAll()
            pdfCacheBytes = 0
            lastMessage = "PDF 缓存已清理。"
        } catch {
            lastError = error.localizedDescription
        }
    }

    func filteredPapers(_ papers: [PaperRecord], for day: Date? = nil) -> [PaperRecord] {
        let dayText = ArxivBatchCalendar.dayString(day ?? selectedBatchDay)
        let normalizedSearch = searchText.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return papers
            .filter { $0.fetchedForDate == dayText }
            .filter { !showingFavoritesOnly || $0.isFavorite }
            .filter { selectedTopicKey == "all" || $0.topicKey == selectedTopicKey }
            .filter { paper in
                guard !normalizedSearch.isEmpty else { return true }
                let haystack = "\(paper.title) \(paper.authors.joined(separator: " ")) \(paper.affiliations.joined(separator: " ")) \(paper.primaryCategory) \(paper.matchedKeywords.map(\.keyword).joined(separator: " "))".lowercased()
                return haystack.contains(normalizedSearch)
            }
            .sorted {
                if $0.relevanceScore == $1.relevanceScore {
                    return ($0.publishedAt ?? .distantPast) > ($1.publishedAt ?? .distantPast)
                }
                return $0.relevanceScore > $1.relevanceScore
            }
    }

    private func runInsightGeneration(
        kinds: [InsightKind],
        title: String,
        successMessage: String,
        for paper: PaperRecord,
        context: ModelContext,
        settings: AppSettings
    ) {
        guard !kinds.isEmpty else { return }
        activeTask = TaskActivity(title: title, stage: "queued", message: "准备生成内容", percent: 0.02, paperId: paper.arxivId, insightKind: kinds.count == 1 ? kinds[0] : nil)
        lastError = ""
        Task {
            do {
                let generator = InsightGenerator(settings: settings)
                for (index, kind) in kinds.enumerated() {
                    let start = Double(index) / Double(kinds.count)
                    let end = Double(index + 1) / Double(kinds.count)
                    activeTask = TaskActivity(title: kind.progressTitle, stage: "queued", message: "准备\(kind.label)", percent: start, paperId: paper.arxivId, insightKind: kind)
                    try await generate(kind, for: paper, with: generator) { [weak self] progress in
                        self?.activeTask = TaskActivity(
                            title: kind.progressTitle,
                            stage: progress.stage,
                            message: progress.message,
                            percent: start + (end - start) * max(0, min(progress.percent, 1)),
                            paperId: paper.arxivId,
                            insightKind: kind
                        )
                    }
                    try context.save()
                }
                lastMessage = successMessage
                activeTask = TaskActivity(title: title, stage: "complete", message: successMessage, percent: 1, paperId: paper.arxivId, insightKind: kinds.count == 1 ? kinds[0] : nil)
            } catch {
                lastError = error.localizedDescription
                activeTask = TaskActivity(title: title, stage: "failed", message: lastError, percent: 1, paperId: paper.arxivId, insightKind: kinds.count == 1 ? kinds[0] : nil)
            }
        }
    }

    private func generate(_ kind: InsightKind, for paper: PaperRecord, with generator: InsightGenerator, progress: @escaping (InsightProgress) -> Void) async throws {
        switch kind {
        case .translation:
            try await generator.generateTranslation(for: paper, progress: progress)
        case .summary:
            try await generator.generateSummary(for: paper, progress: progress)
        case .fullText:
            try await generator.generateFullText(for: paper, progress: progress)
        }
    }
}

struct TaskActivity: Identifiable, Equatable {
    let id = UUID()
    var title: String
    var stage: String
    var message: String
    var percent: Double
    var paperId: String = ""
    var insightKind: InsightKind?

    var isTerminal: Bool {
        stage == "complete" || stage == "failed"
    }
}
