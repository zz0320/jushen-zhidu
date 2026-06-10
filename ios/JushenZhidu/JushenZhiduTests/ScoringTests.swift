import XCTest
@testable import JushenZhidu

final class ScoringTests: XCTestCase {
    func testScoringMatchesIncludeKeywords() {
        let result = ScoringEngine.score(
            title: "VLA policy learning",
            abstract: "A robot learning system for manipulation.",
            rules: [
                KeywordRuleInput(group: "Foundation", value: "vla", kind: .include, weight: 3.8),
                KeywordRuleInput(group: "Learning", value: "robot learning", kind: .include, weight: 2.8)
            ]
        )

        XCTAssertFalse(result.excluded)
        XCTAssertEqual(result.matched.map(\.keyword), ["vla", "robot learning"])
        XCTAssertGreaterThan(result.score, 6.0)
    }

    func testScoringStopsOnExcludeKeyword() {
        let result = ScoringEngine.score(
            title: "A chatbot for web robot automation",
            abstract: "Not a robotics paper.",
            rules: [
                KeywordRuleInput(group: "Learning", value: "robot", kind: .include, weight: 2.0),
                KeywordRuleInput(group: "Learning", value: "chatbot", kind: .exclude, weight: 2.0)
            ]
        )

        XCTAssertTrue(result.excluded)
        XCTAssertEqual(result.score, 0)
        XCTAssertTrue(result.matched.isEmpty)
    }

    func testTopicClassifierPrefersFoundationSignals() {
        let topic = TopicClassifier.classify(
            title: "Vision-Language-Action World Model",
            abstract: "A generalist robot policy.",
            keywords: [],
            categories: ["cs.RO"]
        )

        XCTAssertEqual(topic.key, "foundation")
    }

    func testResearchTopicSpritesAreStableWithinTopic() {
        let topics = ResearchTopic.filterTopics
        let matureSprites = topics.map { $0.spriteAssetName(tier: .mature, seed: "paper-a") }
        XCTAssertEqual(Set(matureSprites).count, topics.count)

        for topic in topics {
            XCTAssertEqual(
                topic.spriteAssetName(tier: .mature, seed: "paper-a"),
                topic.spriteAssetName(tier: .mature, seed: "paper-b")
            )
        }
    }

    func testPlantTierUsesSaplingUntilAnyInsightExists() {
        XCTAssertEqual(PlantTier(count: 0), .sapling)
        XCTAssertEqual(PlantTier(count: 1), .mature)
        XCTAssertEqual(PlantTier(count: 2), .mature)
        XCTAssertEqual(PlantTier(count: 3), .mature)
    }

    func testMissingInsightKindsTrackCompletedFields() {
        let paper = Self.makePaper()
        XCTAssertEqual(paper.missingInsightKinds, [.translation, .summary, .fullText])

        paper.translationContent = "中文摘要"
        XCTAssertEqual(paper.missingInsightKinds, [.summary, .fullText])

        paper.summaryContent = "速读总结"
        paper.fullTextSummaryContent = "深读总结"
        XCTAssertTrue(paper.missingInsightKinds.isEmpty)
        XCTAssertEqual(paper.insightCompletionCount, 3)
    }

    func testMarkdownBlockParserHandlesSummarySyntax() {
        let blocks = MarkdownBlockParser.parse("""
        基于 PDF 提取。

        ---

        ### 1. 研究问题
        GEAR-VLA 聚焦于**Vision-Language-Action**模型。
        - **动作表征断裂**：tokenization 存在问题

        $$
        R(s, a) = \\sum_i w_i r_i(s, a)
        $$
        """)

        XCTAssertEqual(blocks.first, .paragraph("基于 PDF 提取。"))
        XCTAssertTrue(blocks.contains(.rule))
        XCTAssertTrue(blocks.contains(.heading(level: 3, text: "1. 研究问题")))
        XCTAssertTrue(blocks.contains(.bullet("**动作表征断裂**：tokenization 存在问题")))
        XCTAssertTrue(blocks.contains { block in
            if case .formula(let formula) = block {
                return formula.contains("R(s, a)")
            }
            return false
        })
    }

    func testSummaryExcerptRemovesMarkdownSyntax() {
        let excerpt = """
        基于 arXiv 元数据与摘要，总结如下：

        ---
        **1. 研究问题** 如何提升 **VLA** 模型表现。
        - **动作表征断裂**：tokenization 问题。
        """.summaryExcerpt(limit: 120)

        XCTAssertFalse(excerpt.contains("---"))
        XCTAssertFalse(excerpt.contains("**"))
        XCTAssertTrue(excerpt.contains("研究问题"))
        XCTAssertTrue(excerpt.contains("VLA"))
    }

    @MainActor
    func testFetchLimitDefaultsAndPersists() {
        let suiteName = "JushenZhiduTests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer {
            defaults.removePersistentDomain(forName: suiteName)
        }

        let keychain = KeychainStore(service: "com.kenton.JushenZhiduTests.\(UUID().uuidString)")
        let settings = AppSettings(defaults: defaults, keychain: keychain)
        XCTAssertEqual(settings.fetchLimit, 200)

        settings.fetchLimit = 450
        settings.save()

        let restored = AppSettings(defaults: defaults, keychain: keychain)
        XCTAssertEqual(restored.fetchLimit, 450)

        restored.fetchLimit = 1_200
        restored.saveFetchLimit()
        XCTAssertEqual(restored.fetchLimit, 1_000)
    }

    func testKeychainRoundTrip() throws {
        let service = "com.kenton.JushenZhiduTests.\(UUID().uuidString)"
        let keychain = KeychainStore(service: service)

        try keychain.save("secret", account: "api-key")
        XCTAssertEqual(try keychain.read(account: "api-key"), "secret")
        try keychain.delete(account: "api-key")
        XCTAssertEqual(try keychain.read(account: "api-key"), "")
    }

    private static func makePaper() -> PaperRecord {
        PaperRecord(
            arxivId: "2606.00001v1",
            title: "Vision-Language-Action Policy",
            abstract: "A robot learning paper.",
            authors: ["A. Researcher"],
            affiliations: [],
            primaryCategory: "cs.RO",
            categories: ["cs.RO"],
            publishedAt: nil,
            updatedAt: nil,
            absURL: "https://arxiv.org/abs/2606.00001",
            pdfURL: "https://arxiv.org/pdf/2606.00001",
            fetchedForDate: "2026-06-09",
            relevanceScore: 12,
            matchedKeywords: [],
            topicKey: "foundation"
        )
    }
}
