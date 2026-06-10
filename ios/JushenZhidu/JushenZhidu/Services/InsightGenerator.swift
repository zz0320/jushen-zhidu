import Foundation
import PDFKit
import SwiftData

enum InsightGenerationError: LocalizedError {
    case missingAPIKey
    case invalidBaseURL
    case invalidModelResponse
    case missingPDF
    case pdfDownloadFailed

    var errorDescription: String? {
        switch self {
        case .missingAPIKey:
            return "请先在设置里配置模型 API Key。"
        case .invalidBaseURL:
            return "模型 Base URL 无法识别。"
        case .invalidModelResponse:
            return "模型返回内容无法解析。"
        case .missingPDF:
            return "这篇论文没有可用的 PDF 链接。"
        case .pdfDownloadFailed:
            return "PDF 下载或缓存失败。"
        }
    }
}

struct InsightProgress: Equatable {
    var stage: String
    var message: String
    var percent: Double
}

struct ModelCompletionResult {
    let content: String
    let model: String
}

@MainActor
struct InsightGenerator {
    let settings: AppSettings

    func generateAll(for paper: PaperRecord, progress: @escaping (InsightProgress) -> Void) async throws {
        progress(InsightProgress(stage: "preparing", message: "整理论文上下文", percent: 0.08))
        try await generateTranslation(for: paper) { progress(Self.scaled($0, from: 0.08, to: 0.34)) }
        try await generateSummary(for: paper) { progress(Self.scaled($0, from: 0.34, to: 0.58)) }
        try await generateFullText(for: paper) { progress(Self.scaled($0, from: 0.58, to: 0.98)) }
        progress(InsightProgress(stage: "complete", message: "智能阅读包已完成", percent: 1.0))
    }

    func generateTranslation(for paper: PaperRecord, progress: @escaping (InsightProgress) -> Void) async throws {
        progress(InsightProgress(stage: "translation", message: "生成题目与摘要中文翻译", percent: 0.12))
        let runtime = try runtimeSettings()
        let translation = try await complete(messages: Self.translationMessages(for: paper), maxTokens: settings.maxTokensSingle, model: runtime.chatModel, runtime: runtime)
        let parsedTranslation = Self.parseTranslation(translation.content)
        paper.translationTitle = parsedTranslation.title
        paper.translationContent = parsedTranslation.abstract
        paper.translationModel = translation.model
        paper.translationGeneratedAt = Date()
        progress(InsightProgress(stage: "complete", message: "译文已完成", percent: 1.0))
    }

    func generateSummary(for paper: PaperRecord, progress: @escaping (InsightProgress) -> Void) async throws {
        progress(InsightProgress(stage: "summary", message: "生成摘要版研究总结", percent: 0.16))
        let runtime = try runtimeSettings()
        let summary = try await complete(messages: Self.summaryMessages(for: paper), maxTokens: settings.maxTokensSingle, model: runtime.chatModel, runtime: runtime)
        paper.summaryContent = summary.content
        paper.summaryModel = summary.model
        paper.summaryGeneratedAt = Date()
        progress(InsightProgress(stage: "complete", message: "速读已完成", percent: 1.0))
    }

    func generateFullText(for paper: PaperRecord, progress: @escaping (InsightProgress) -> Void) async throws {
        let runtime = try runtimeSettings()
        progress(InsightProgress(stage: "pdf", message: "下载并提取 PDF 正文", percent: 0.18))
        let extraction = try await PDFTextExtractor(maxCharacters: settings.fullTextMaxCharacters, figureLimit: settings.fullTextFigureLimit).extract(from: paper)
        paper.figurePagesJSON = JSONCoding.encode(extraction.figurePages)
        paper.fullTextSourceURL = extraction.sourceURL
        paper.fullTextSourceChars = extraction.sourceCharacters
        paper.fullTextUsedChars = extraction.usedCharacters
        paper.fullTextTruncated = extraction.truncated

        progress(InsightProgress(stage: "fullText", message: "生成全文深读总结", percent: 0.62))
        let fullText = try await complete(
            messages: Self.fullTextMessages(for: paper, extraction: extraction),
            maxTokens: settings.maxTokensFullText,
            model: runtime.chatModel,
            runtime: runtime
        )
        paper.fullTextSummaryContent = fullText.content
        paper.fullTextSummaryModel = fullText.model
        paper.fullTextGeneratedAt = Date()
        progress(InsightProgress(stage: "complete", message: "深读已完成", percent: 1.0))
    }

    private func runtimeSettings() throws -> RuntimeSettings {
        let apiKey = settings.apiKey.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !apiKey.isEmpty else { throw InsightGenerationError.missingAPIKey }
        guard let baseURL = settings.normalizedBaseURL else { throw InsightGenerationError.invalidBaseURL }
        return RuntimeSettings(
            baseURL: baseURL,
            apiKey: apiKey,
            chatModel: settings.chatModel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? "qwen-plus" : settings.chatModel,
            temperature: settings.temperature
        )
    }

    private func complete(messages: [ChatMessage], maxTokens: Int, model: String, runtime: RuntimeSettings) async throws -> ModelCompletionResult {
        var endpoint = runtime.baseURL
        if endpoint.lastPathComponent != "chat" {
            endpoint.appendPathComponent("chat")
        }
        endpoint.appendPathComponent("completions")
        var request = URLRequest(url: endpoint)
        request.httpMethod = "POST"
        request.timeoutInterval = 90
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("Bearer \(runtime.apiKey)", forHTTPHeaderField: "Authorization")
        let payload = ChatCompletionRequest(model: model, messages: messages, temperature: runtime.temperature, maxTokens: maxTokens)
        request.httpBody = try JSONEncoder().encode(payload)
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse, 200..<300 ~= http.statusCode else {
            throw InsightGenerationError.invalidModelResponse
        }
        let decoded = try JSONDecoder().decode(ChatCompletionResponse.self, from: data)
        guard let choice = decoded.choices.first, !choice.message.content.isEmpty else {
            throw InsightGenerationError.invalidModelResponse
        }
        return ModelCompletionResult(content: choice.message.content.trimmingCharacters(in: .whitespacesAndNewlines), model: decoded.model)
    }

    static func translationMessages(for paper: PaperRecord) -> [ChatMessage] {
        [
            ChatMessage(role: "system", content: "你是专业的英中科研论文翻译助手，熟悉具身智能、机器人学习、VLA 和多模态模型术语。只输出 JSON，不要 Markdown。"),
            ChatMessage(role: "user", content: """
            请将下面 arXiv 论文标题和 Abstract 翻译成中文。JSON 字段必须是 title_zh 和 abstract_zh。

            Title: \(paper.title)

            Abstract: \(paper.abstract)
            """)
        ]
    }

    static func summaryMessages(for paper: PaperRecord) -> [ChatMessage] {
        [
            ChatMessage(role: "system", content: "你是具身智能、机器人学习和多模态模型方向的研究助理。中文输出，保留关键英文术语，不要编造论文没有的信息。"),
            ChatMessage(role: "user", content: """
            请基于 arXiv 元数据和摘要总结这篇论文，结构为：
            1. 研究问题
            2. 方法概述
            3. 数据 / benchmark
            4. 机器人平台或任务
            5. 主要结果
            6. 值得关注点
            7. 局限性或需要深读的问题

            arXiv ID: \(paper.arxivId)
            Title: \(paper.title)
            Authors: \(paper.authors.prefix(8).joined(separator: ", "))
            Categories: \(paper.categories.joined(separator: ", "))
            Matched keywords: \(paper.matchedKeywords.map(\.keyword).joined(separator: ", "))
            Abstract: \(paper.abstract)
            """)
        ]
    }

    static func fullTextMessages(for paper: PaperRecord, extraction: PDFExtractionResult) -> [ChatMessage] {
        [
            ChatMessage(role: "system", content: "你是具身智能、机器人学习和多模态模型方向的研究助理。请基于 PDF 提取文本做全文总结，明确截断和不确定性。"),
            ChatMessage(role: "user", content: """
            请按以下结构进行全文深度总结，并在开头注明：基于 arXiv PDF 文本提取。
            1. 研究问题
            2. 方法概述
            3. 数据 / benchmark
            4. 机器人平台或任务
            5. 实验设置与主要结果
            6. 实现细节或关键设计
            7. 值得关注点
            8. 局限性或需要深读的问题

            Title: \(paper.title)
            arXiv ID: \(paper.arxivId)
            PDF source: \(extraction.sourceURL)
            Text usage: \(extraction.usedCharacters) / \(extraction.sourceCharacters), truncated: \(extraction.truncated)

            Extracted PDF text:
            \(extraction.text)
            """)
        ]
    }

    static func parseTranslation(_ raw: String) -> (title: String, abstract: String) {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines).strippingJSONFence()
        if let data = trimmed.data(using: .utf8),
           let payload = try? JSONDecoder().decode(TranslationPayload.self, from: data) {
            return (payload.titleZh ?? payload.title ?? "", payload.abstractZh ?? payload.abstract ?? "")
        }
        var title = ""
        var abstractLines: [String] = []
        for line in raw.components(separatedBy: .newlines) {
            if line.localizedCaseInsensitiveContains("标题") || line.localizedCaseInsensitiveContains("title") {
                title = line.components(separatedBy: CharacterSet(charactersIn: ":：")).dropFirst().joined(separator: "：").trimmingCharacters(in: .whitespaces)
            } else if !line.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                abstractLines.append(line)
            }
        }
        return (title, abstractLines.joined(separator: "\n"))
    }

    private static func scaled(_ progress: InsightProgress, from start: Double, to end: Double) -> InsightProgress {
        InsightProgress(
            stage: progress.stage,
            message: progress.message,
            percent: start + (end - start) * max(0, min(progress.percent, 1))
        )
    }
}

struct PDFExtractionResult {
    let text: String
    let sourceURL: String
    let sourceCharacters: Int
    let usedCharacters: Int
    let truncated: Bool
    let figurePages: [PaperFigurePage]
}

struct PDFTextExtractor {
    let maxCharacters: Int
    let figureLimit: Int

    func extract(from paper: PaperRecord) async throws -> PDFExtractionResult {
        let cachedFile = try await PaperPDFCache.storePDF(for: paper)
        let document = PDFDocument(url: cachedFile.url)
        var textParts: [String] = []
        var figures: [PaperFigurePage] = []
        let pageCount = document?.pageCount ?? 0
        for index in 0..<pageCount {
            guard let page = document?.page(at: index) else { continue }
            let pageText = page.string?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            if !pageText.isEmpty {
                textParts.append("Page \(index + 1)\n\(pageText)")
            }
            if figures.count < figureLimit, index > 0 {
                figures.append(PaperFigurePage(page: index + 1, label: "PDF 第 \(index + 1) 页", reason: "可在论文中检查方法图、实验图或关键表格。"))
            }
        }
        let source = textParts.joined(separator: "\n\n")
        let sourceCharacters = source.count
        let usedText = String(source.prefix(maxCharacters))
        return PDFExtractionResult(
            text: usedText,
            sourceURL: cachedFile.sourceURL,
            sourceCharacters: sourceCharacters,
            usedCharacters: usedText.count,
            truncated: sourceCharacters > usedText.count,
            figurePages: figures
        )
    }
}

struct CachedPaperPDF: Identifiable, Hashable {
    var id: String { url.path }
    let url: URL
    let sourceURL: String
    let bytes: Int64
    let cachedAt: Date
}

enum PaperPDFCache {
    static func cachedPDF(for paper: PaperRecord) -> CachedPaperPDF? {
        let url = cacheURL(for: paper)
        guard FileManager.default.fileExists(atPath: url.path),
              isPDFFile(url),
              let values = try? url.resourceValues(forKeys: [.fileSizeKey, .contentModificationDateKey]) else {
            if FileManager.default.fileExists(atPath: url.path) {
                try? FileManager.default.removeItem(at: url)
            }
            return nil
        }
        return CachedPaperPDF(
            url: url,
            sourceURL: paper.pdfURL,
            bytes: Int64(values.fileSize ?? 0),
            cachedAt: values.contentModificationDate ?? Date()
        )
    }

    static func storePDF(for paper: PaperRecord) async throws -> CachedPaperPDF {
        if let cached = cachedPDF(for: paper) {
            return cached
        }
        guard let source = URL(string: paper.pdfURL), !paper.pdfURL.isEmpty else {
            throw InsightGenerationError.missingPDF
        }
        let (data, response) = try await URLSession.shared.data(from: source)
        guard let http = response as? HTTPURLResponse,
              200..<300 ~= http.statusCode,
              data.starts(with: Data("%PDF".utf8)) else {
            throw InsightGenerationError.pdfDownloadFailed
        }
        let directory = cacheDirectory
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let target = cacheURL(for: paper)
        try data.write(to: target, options: [.atomic])
        return CachedPaperPDF(url: target, sourceURL: paper.pdfURL, bytes: Int64(data.count), cachedAt: Date())
    }

    static func removePDF(for paper: PaperRecord) throws {
        let url = cacheURL(for: paper)
        if FileManager.default.fileExists(atPath: url.path) {
            try FileManager.default.removeItem(at: url)
        }
    }

    static func removeAll() throws {
        let directory = cacheDirectory
        if FileManager.default.fileExists(atPath: directory.path) {
            try FileManager.default.removeItem(at: directory)
        }
    }

    static func totalSize() -> Int64 {
        let directory = cacheDirectory
        guard let enumerator = FileManager.default.enumerator(at: directory, includingPropertiesForKeys: [.fileSizeKey]) else {
            return 0
        }
        return enumerator.compactMap { item -> Int64? in
            guard let url = item as? URL,
                  let values = try? url.resourceValues(forKeys: [.fileSizeKey]) else {
                return nil
            }
            return Int64(values.fileSize ?? 0)
        }.reduce(0, +)
    }

    static func cacheURL(for paper: PaperRecord) -> URL {
        cacheDirectory.appendingPathComponent("\(safeFileName(paper.arxivId)).pdf")
    }

    private static var cacheDirectory: URL {
        FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Papers", isDirectory: true)
    }

    private static func safeFileName(_ value: String) -> String {
        let allowed = CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_."))
        let fileName = value.unicodeScalars.map { allowed.contains($0) ? String($0) : "-" }.joined()
        let trimmed = fileName.trimmingCharacters(in: CharacterSet(charactersIn: "-"))
        return trimmed.isEmpty ? UUID().uuidString : trimmed
    }

    private static func isPDFFile(_ url: URL) -> Bool {
        guard let handle = try? FileHandle(forReadingFrom: url) else {
            return false
        }
        defer {
            try? handle.close()
        }
        let header = (try? handle.read(upToCount: 4)) ?? Data()
        return header.starts(with: Data("%PDF".utf8))
    }
}

private struct RuntimeSettings {
    let baseURL: URL
    let apiKey: String
    let chatModel: String
    let temperature: Double
}

private struct ChatCompletionRequest: Encodable {
    let model: String
    let messages: [ChatMessage]
    let temperature: Double
    let maxTokens: Int

    enum CodingKeys: String, CodingKey {
        case model
        case messages
        case temperature
        case maxTokens = "max_tokens"
    }
}

struct ChatMessage: Codable, Hashable {
    let role: String
    let content: String
}

private struct ChatCompletionResponse: Decodable {
    let model: String
    let choices: [Choice]

    struct Choice: Decodable {
        let message: ChatMessage
    }
}

private struct TranslationPayload: Decodable {
    let titleZh: String?
    let abstractZh: String?
    let title: String?
    let abstract: String?

    enum CodingKeys: String, CodingKey {
        case titleZh = "title_zh"
        case abstractZh = "abstract_zh"
        case title
        case abstract
    }
}

private extension String {
    func strippingJSONFence() -> String {
        var value = trimmingCharacters(in: .whitespacesAndNewlines)
        if value.hasPrefix("```") {
            value = value.replacingOccurrences(of: "```json", with: "")
            value = value.replacingOccurrences(of: "```", with: "")
        }
        return value.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
