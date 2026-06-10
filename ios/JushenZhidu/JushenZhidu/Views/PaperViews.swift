import SwiftData
import SwiftUI
import PDFKit

#if canImport(Translation)
import Translation
#endif

struct PapersListView: View {
    @Environment(\.modelContext) private var modelContext
    @EnvironmentObject private var library: LibraryViewModel
    @EnvironmentObject private var settings: AppSettings
    @Query private var papers: [PaperRecord]
    let favoritesOnly: Bool

    private var visiblePapers: [PaperRecord] {
        var rows = library.filteredPapers(papers)
        if favoritesOnly {
            rows = rows.filter(\.isFavorite)
        }
        return rows
    }

    var body: some View {
        NavigationStack {
            ZStack {
                ForestBackground()
                ScrollView {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                        BatchHeaderView(
                            title: favoritesOnly ? "我的收藏" : "单篇论文",
                            subtitle: "arXiv 公告批次 \(library.selectedBatchDayText)",
                            paperCount: visiblePapers.count,
                            matchedCount: visiblePapers.count,
                            onPrevious: { library.previousBatchDay() },
                            onNext: { library.nextBatchDay() },
                            onFetch: { library.fetchCurrentBatch(context: modelContext, settings: settings) }
                        )

                        ResearchSearchField(text: $library.searchText, placeholder: "搜索标题、作者、机构、关键词")

                        if visiblePapers.isEmpty {
                            EmptyPaperListState(favoritesOnly: favoritesOnly)
                        } else {
                            LazyVStack(spacing: AppTheme.Spacing.md) {
                                ForEach(Array(visiblePapers.enumerated()), id: \.element.arxivId) { index, paper in
                                    NavigationLink {
                                        PaperDetailView(paper: paper)
                                    } label: {
                                        PaperCardView(paper: paper, rank: index + 1)
                                    }
                                    .buttonStyle(.forestPress)
                                }
                            }
                        }
                    }
                    .padding(AppTheme.Spacing.lg)
                }
            }
            .navigationTitle(favoritesOnly ? "收藏" : "论文")
            .navigationBarTitleDisplayMode(.inline)
        }
    }
}

struct PaperCardView: View {
    @Environment(\.modelContext) private var modelContext
    @EnvironmentObject private var library: LibraryViewModel
    @EnvironmentObject private var settings: AppSettings
    let paper: PaperRecord
    let rank: Int

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
                PaperForestThumbnail(paper: paper, size: 74)

                VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                    HStack(spacing: AppTheme.Spacing.sm) {
                        Text("#\(rank)")
                            .font(AppTheme.Typography.metricSmall)
                            .foregroundStyle(Color.white)
                            .padding(.horizontal, AppTheme.Spacing.sm)
                            .padding(.vertical, AppTheme.Spacing.xs)
                            .background(AppTheme.ColorToken.canopy, in: Capsule())
                        Text(String(format: "%.1f", paper.relevanceScore))
                            .font(AppTheme.Typography.metricSmall)
                            .foregroundStyle(AppTheme.ColorToken.warmAction)
                        Text(paper.primaryCategory)
                            .font(AppTheme.Typography.englishCaption)
                            .foregroundStyle(AppTheme.ColorToken.arxivBlue)
                    }
                    Text(paper.title)
                        .font(AppTheme.Typography.englishCardTitle)
                        .foregroundStyle(AppTheme.ColorToken.ink)
                        .multilineTextAlignment(.leading)
                    if !paper.translationTitle.isEmpty {
                        Text(paper.translationTitle)
                            .font(AppTheme.Typography.bodyEmphasis)
                            .foregroundStyle(AppTheme.ColorToken.arxivBlue)
                            .multilineTextAlignment(.leading)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                Spacer()
                Button {
                    library.toggleFavorite(paper, context: modelContext)
                } label: {
                    Image(systemName: paper.isFavorite ? "bookmark.fill" : "bookmark")
                        .foregroundStyle(paper.isFavorite ? AppTheme.ColorToken.warmAction : AppTheme.ColorToken.mossDark)
                        .stableIconButtonStyle()
                }
                .accessibilityLabel(paper.isFavorite ? "取消收藏" : "收藏")
            }

            Text(paper.authors.prefix(5).joined(separator: ", "))
                .font(AppTheme.Typography.englishFootnote)
                .foregroundStyle(AppTheme.ColorToken.mutedInk)
                .lineLimit(2)

            KeywordChips(keywords: Array(paper.matchedKeywords.prefix(5).map(\.keyword)))

            if !paper.summaryContent.isEmpty || !paper.fullTextSummaryContent.isEmpty {
                Text((paper.summaryContent.isEmpty ? paper.fullTextSummaryContent : paper.summaryContent).summaryExcerpt(limit: 180))
                    .font(AppTheme.Typography.footnote)
                    .foregroundStyle(AppTheme.ColorToken.ink)
                    .lineLimit(4)
                    .padding(AppTheme.Spacing.md)
                    .background(AppTheme.ColorToken.paper, in: RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous))
            }

            HStack {
                InsightStatusView(paper: paper)
                Spacer()
                Button {
                    library.completeMissingInsights(for: paper, context: modelContext, settings: settings)
                } label: {
                    Label(paper.hasFullInsightPack ? "刷新" : "补全", systemImage: "sparkles")
                        .font(AppTheme.Typography.captionStrong)
                }
                .buttonStyle(.bordered)
            }
        }
        .forestCard()
    }
}

struct InsightStatusView: View {
    let paper: PaperRecord

    var body: some View {
        HStack(spacing: AppTheme.Spacing.xs) {
            InsightProgressRing(completed: paper.insightCompletionCount)
            InsightDot(label: "译", systemImage: "character.book.closed", done: !paper.translationContent.isEmpty)
            InsightDot(label: "摘", systemImage: "text.badge.checkmark", done: !paper.summaryContent.isEmpty)
            InsightDot(label: "全", systemImage: "doc.richtext", done: !paper.fullTextSummaryContent.isEmpty)
        }
        .accessibilityLabel("智能状态：译文\(paper.translationContent.isEmpty ? "未完成" : "已完成")，摘要\(paper.summaryContent.isEmpty ? "未完成" : "已完成")，全文\(paper.fullTextSummaryContent.isEmpty ? "未完成" : "已完成")")
    }
}

struct InsightProgressRing: View {
    let completed: Int

    private var progress: CGFloat {
        CGFloat(min(max(completed, 0), 3)) / 3
    }

    var body: some View {
        ZStack {
            Circle()
                .stroke(AppTheme.ColorToken.paperDeep, lineWidth: 4)
            Circle()
                .trim(from: 0, to: progress)
                .stroke(ringColor, style: StrokeStyle(lineWidth: 4, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .animation(AppTheme.Motion.status, value: progress)
            Text("\(completed)")
                .font(AppTheme.Typography.metricTiny)
                .foregroundStyle(AppTheme.ColorToken.ink)
                .contentTransition(.numericText())
        }
        .frame(width: 32, height: 32)
        .accessibilityHidden(true)
    }

    private var ringColor: Color {
        completed == 3 ? AppTheme.ColorToken.success : AppTheme.ColorToken.warmAction
    }
}

struct InsightDot: View {
    let label: String
    let systemImage: String
    let done: Bool

    var body: some View {
        ZStack {
            Circle()
                .fill(done ? AppTheme.ColorToken.success : AppTheme.ColorToken.paperDeep)
                .frame(width: 30, height: 30)
            Image(systemName: systemImage)
                .font(AppTheme.Typography.captionSmallStrong)
                .foregroundStyle(done ? Color.white : AppTheme.ColorToken.mossMuted)
        }
        .scaleEffect(done ? 1 : 0.94)
        .animation(AppTheme.Motion.control, value: done)
        .accessibilityLabel(label)
    }
}

struct KeywordChips: View {
    let keywords: [String]

    var body: some View {
        if !keywords.isEmpty {
            ChipFlowLayout(horizontalSpacing: AppTheme.Spacing.xs, verticalSpacing: AppTheme.Spacing.xs) {
                ForEach(keywords, id: \.self) { keyword in
                    Text(keyword)
                        .font(AppTheme.Typography.englishCaption)
                        .lineLimit(1)
                        .truncationMode(.tail)
                        .padding(.horizontal, AppTheme.Spacing.sm)
                        .padding(.vertical, AppTheme.Spacing.xs)
                        .background(AppTheme.ColorToken.paperDeep, in: Capsule())
                        .foregroundStyle(AppTheme.ColorToken.mossDark)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

struct ChipFlowLayout: Layout {
    var horizontalSpacing: CGFloat
    var verticalSpacing: CGFloat

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let maxWidth = proposal.width ?? .greatestFiniteMagnitude
        let rows = rows(in: maxWidth, subviews: subviews)
        let height = rows.reduce(CGFloat.zero) { partial, row in
            partial + row.height
        } + CGFloat(max(rows.count - 1, 0)) * verticalSpacing
        let width = proposal.width ?? rows.map(\.width).max() ?? 0
        return CGSize(width: width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let rows = rows(in: bounds.width, subviews: subviews)
        var y = bounds.minY
        for row in rows {
            var x = bounds.minX
            for item in row.items {
                subviews[item.index].place(
                    at: CGPoint(x: x, y: y),
                    anchor: .topLeading,
                    proposal: ProposedViewSize(item.size)
                )
                x += item.size.width + horizontalSpacing
            }
            y += row.height + verticalSpacing
        }
    }

    private func rows(in maxWidth: CGFloat, subviews: Subviews) -> [ChipLayoutRow] {
        var rows: [ChipLayoutRow] = []
        var current = ChipLayoutRow()

        for index in subviews.indices {
            let size = subviews[index].sizeThatFits(.unspecified)
            let proposedWidth = current.items.isEmpty ? size.width : current.width + horizontalSpacing + size.width
            if !current.items.isEmpty, proposedWidth > maxWidth {
                rows.append(current)
                current = ChipLayoutRow()
            }
            current.append(index: index, size: size, spacing: horizontalSpacing)
        }

        if !current.items.isEmpty {
            rows.append(current)
        }
        return rows
    }
}

private struct ChipLayoutRow {
    var items: [(index: Int, size: CGSize)] = []
    var width: CGFloat = 0
    var height: CGFloat = 0

    mutating func append(index: Int, size: CGSize, spacing: CGFloat) {
        if !items.isEmpty {
            width += spacing
        }
        items.append((index, size))
        width += size.width
        height = max(height, size.height)
    }
}

struct PaperDetailView: View {
    @Environment(\.modelContext) private var modelContext
    @Environment(\.openURL) private var openURL
    @EnvironmentObject private var library: LibraryViewModel
    @EnvironmentObject private var settings: AppSettings
    let paper: PaperRecord
    @State private var section: PaperDetailSection = .abstract
    @State private var pdfReaderItem: PDFReaderItem?
    @State private var pdfError = ""

    var body: some View {
        ZStack {
            ForestBackground()
            ScrollView {
                VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                    PaperDetailHero(paper: paper)

                    Picker("内容", selection: $section) {
                        ForEach(PaperDetailSection.allCases) { item in
                            Text(item.label).tag(item)
                        }
                    }
                    .pickerStyle(.segmented)

                    detailSection

                    PaperDetailActionPanel(
                        paper: paper,
                        pdfError: pdfError,
                        openReader: openPDFReader
                    )
                }
                .padding(AppTheme.Spacing.lg)
            }
        }
        .navigationTitle("论文详情")
        .navigationBarTitleDisplayMode(.inline)
        .sheet(item: $pdfReaderItem) { item in
            PDFReaderSheet(item: item)
        }
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                if let url = URL(string: paper.absURL), !paper.absURL.isEmpty {
                    Button {
                        openURL(url)
                    } label: {
                        Image(systemName: "a.circle")
                    }
                    .accessibilityLabel("打开 arXiv")
                }
                if let url = URL(string: paper.pdfURL), !paper.pdfURL.isEmpty {
                    Button {
                        openURL(url)
                    } label: {
                        Image(systemName: "doc")
                    }
                    .accessibilityLabel("打开 PDF")
                }
            }
        }
    }

    private func openPDFReader() {
        pdfError = ""
        if let cached = library.cachedPDF(for: paper) {
            pdfReaderItem = PDFReaderItem(paperTitle: paper.title, file: cached)
            return
        }
        Task {
            do {
                let cached = try await library.preparePDF(for: paper)
                library.activeTask = nil
                pdfReaderItem = PDFReaderItem(paperTitle: paper.title, file: cached)
            } catch {
                pdfError = error.localizedDescription
            }
        }
    }

    @ViewBuilder
    private var detailSection: some View {
        switch section {
        case .abstract:
            BilingualAbstractView(paper: paper)
        case .summary:
            SummaryBlock(title: "摘要版总结", systemImage: "text.badge.checkmark", content: paper.summaryContent, emptyText: "还没有生成摘要总结。")
        case .fullText:
            SummaryBlock(title: "全文总结", systemImage: "doc.richtext", content: paper.fullTextSummaryContent, emptyText: "还没有生成全文总结。")
        case .figures:
            FigurePagesView(paper: paper)
        }
    }
}

enum PaperDetailSection: String, CaseIterable, Identifiable {
    case abstract
    case summary
    case fullText
    case figures

    var id: String { rawValue }

    var label: String {
        switch self {
        case .abstract:
            return "摘要"
        case .summary:
            return "总结"
        case .fullText:
            return "全文"
        case .figures:
            return "图册"
        }
    }
}

struct PaperDetailHero: View {
    let paper: PaperRecord

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
                PaperForestThumbnail(paper: paper, size: 88)
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    HStack(spacing: AppTheme.Spacing.sm) {
                        Text(paper.topic.labelZh)
                            .font(AppTheme.Typography.captionStrong)
                            .padding(.horizontal, AppTheme.Spacing.sm)
                            .padding(.vertical, AppTheme.Spacing.xs)
                            .background(AppTheme.ColorToken.paperDeep, in: Capsule())
                        Text(String(format: "Score %.1f", paper.relevanceScore))
                            .font(AppTheme.Typography.englishCaption)
                            .foregroundStyle(AppTheme.ColorToken.warmAction)
                        Spacer()
                    }
                    Text(paper.title)
                        .font(AppTheme.Typography.screenTitle)
                        .foregroundStyle(AppTheme.ColorToken.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    if !paper.translationTitle.isEmpty {
                        Text(paper.translationTitle)
                            .font(AppTheme.Typography.cardTitle)
                            .foregroundStyle(AppTheme.ColorToken.arxivBlue)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            HStack(alignment: .center) {
                Text(paper.authors.joined(separator: ", "))
                    .font(AppTheme.Typography.englishLabel)
                    .foregroundStyle(AppTheme.ColorToken.mutedInk)
                    .lineLimit(3)
                Spacer(minLength: AppTheme.Spacing.md)
                InsightStatusView(paper: paper)
            }
            if !paper.affiliations.isEmpty {
                Text("单位：\(paper.affiliations.prefix(4).joined(separator: "；"))")
                    .font(AppTheme.Typography.englishFootnote)
                    .foregroundStyle(AppTheme.ColorToken.mutedInk)
            }
            KeywordChips(keywords: paper.matchedKeywords.map(\.keyword))
        }
        .forestCard()
    }
}

struct BilingualAbstractView: View {
    let paper: PaperRecord

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            SummaryBlock(
                title: "English Abstract",
                systemImage: "text.alignleft",
                content: paper.abstract,
                emptyText: "",
                titleFont: AppTheme.Typography.englishHeading,
                contentFont: AppTheme.Typography.englishBody,
                contentLineSpacing: 5
            )
            SummaryBlock(title: "中文摘要", systemImage: "character.book.closed", content: paper.translationContent, emptyText: "还没有生成题目和摘要中文翻译。")
        }
    }
}

struct SummaryBlock: View {
    let title: String
    let systemImage: String
    let content: String
    let emptyText: String
    var titleFont: Font = AppTheme.Typography.cardTitle
    var contentFont: Font = AppTheme.Typography.body
    var contentLineSpacing: CGFloat = 0

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack(alignment: .center) {
                Label(title, systemImage: systemImage)
                    .font(titleFont)
                    .foregroundStyle(AppTheme.ColorToken.ink)
                Spacer()
                NativeTranslationButton(text: content)
            }
            if content.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                Text(emptyText)
                    .font(AppTheme.Typography.label)
                    .foregroundStyle(AppTheme.ColorToken.mutedInk)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(AppTheme.Spacing.lg)
                    .background(AppTheme.ColorToken.paperDeep, in: RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous))
            } else {
                MarkdownContentView(content: content, baseFont: contentFont, lineSpacing: contentLineSpacing)
                    .textSelection(.enabled)
            }
        }
        .forestCard()
    }
}

struct MarkdownContentView: View {
    let content: String
    let baseFont: Font
    let lineSpacing: CGFloat

    private var blocks: [MarkdownBlock] {
        MarkdownBlockParser.parse(content)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in
                blockView(block)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder
    private func blockView(_ block: MarkdownBlock) -> some View {
        switch block {
        case .heading(let level, let text):
            MarkdownInlineText(text: text, font: headingFont(level), lineSpacing: 2)
                .foregroundStyle(AppTheme.ColorToken.ink)
                .padding(.top, level == 1 ? AppTheme.Spacing.sm : AppTheme.Spacing.xs)
        case .paragraph(let text):
            MarkdownInlineText(text: text, font: baseFont, lineSpacing: lineSpacing)
                .foregroundStyle(AppTheme.ColorToken.ink)
        case .bullet(let text):
            HStack(alignment: .firstTextBaseline, spacing: AppTheme.Spacing.sm) {
                Text("•")
                    .font(AppTheme.Typography.chineseLabel)
                    .foregroundStyle(AppTheme.ColorToken.warmAction)
                    .frame(width: 14, alignment: .leading)
                MarkdownInlineText(text: text, font: baseFont, lineSpacing: lineSpacing)
                    .foregroundStyle(AppTheme.ColorToken.ink)
            }
        case .ordered(let number, let text):
            HStack(alignment: .firstTextBaseline, spacing: AppTheme.Spacing.sm) {
                Text("\(number).")
                    .font(AppTheme.Typography.metricSmall)
                    .foregroundStyle(AppTheme.ColorToken.warmAction)
                    .frame(width: 24, alignment: .trailing)
                MarkdownInlineText(text: text, font: baseFont, lineSpacing: lineSpacing)
                    .foregroundStyle(AppTheme.ColorToken.ink)
            }
        case .quote(let text):
            HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
                RoundedRectangle(cornerRadius: 1)
                    .fill(AppTheme.ColorToken.warmAction.opacity(0.72))
                    .frame(width: 3)
                MarkdownInlineText(text: text, font: baseFont, lineSpacing: lineSpacing)
                    .foregroundStyle(AppTheme.ColorToken.mutedInk)
            }
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.ColorToken.vellum.opacity(0.58), in: RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous))
        case .code(let code):
            ScrollView(.horizontal, showsIndicators: false) {
                Text(code)
                    .font(.system(.callout, design: .monospaced))
                    .foregroundStyle(AppTheme.ColorToken.ink)
                    .padding(AppTheme.Spacing.md)
            }
            .background(AppTheme.ColorToken.paperDeep.opacity(0.62), in: RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous))
        case .formula(let formula):
            FormulaBlockView(formula: formula)
        case .rule:
            Rectangle()
                .fill(AppTheme.ColorToken.lineSoft)
                .frame(height: 1)
                .padding(.vertical, AppTheme.Spacing.xs)
        }
    }

    private func headingFont(_ level: Int) -> Font {
        switch level {
        case 1:
            return AppTheme.Typography.screenTitle
        case 2:
            return AppTheme.Typography.sectionTitle
        default:
            return AppTheme.Typography.chineseTitle
        }
    }
}

struct MarkdownInlineText: View {
    let text: String
    let font: Font
    let lineSpacing: CGFloat

    var body: some View {
        Text(markdownAttributedText)
            .font(font)
            .lineSpacing(lineSpacing)
    }

    private var markdownAttributedText: AttributedString {
        let prepared = text.replacingInlineFormulaDelimitersWithCode()
        if let attributed = try? AttributedString(markdown: prepared) {
            return attributed
        }
        return AttributedString(text.strippingInlineFormulaDelimiters())
    }
}

struct FormulaBlockView: View {
    let formula: String

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
            Label("公式", systemImage: "function")
                .font(AppTheme.Typography.chineseCaption)
                .foregroundStyle(AppTheme.ColorToken.arxivBlue)
            ScrollView(.horizontal, showsIndicators: false) {
                Text(formula.trimmingCharacters(in: .whitespacesAndNewlines))
                    .font(.system(.body, design: .monospaced))
                    .foregroundStyle(AppTheme.ColorToken.ink)
                    .padding(.vertical, AppTheme.Spacing.sm)
                    .padding(.horizontal, AppTheme.Spacing.md)
            }
            .background(AppTheme.ColorToken.paper.opacity(0.72), in: RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous))
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.ColorToken.vellum.opacity(0.68), in: RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous)
                .stroke(AppTheme.ColorToken.lineSoft, lineWidth: 1)
        }
    }
}

enum MarkdownBlock: Equatable {
    case heading(level: Int, text: String)
    case paragraph(String)
    case bullet(String)
    case ordered(number: String, text: String)
    case quote(String)
    case code(String)
    case formula(String)
    case rule
}

enum MarkdownBlockParser {
    static func parse(_ raw: String) -> [MarkdownBlock] {
        let lines = raw.replacingOccurrences(of: "\r\n", with: "\n").components(separatedBy: "\n")
        var blocks: [MarkdownBlock] = []
        var paragraph: [String] = []
        var index = 0

        func flushParagraph() {
            let text = paragraph.joined(separator: " ").trimmingCharacters(in: .whitespacesAndNewlines)
            if !text.isEmpty {
                blocks.append(.paragraph(text))
            }
            paragraph.removeAll()
        }

        while index < lines.count {
            let line = lines[index]
            let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)

            if trimmed.isEmpty {
                flushParagraph()
                index += 1
                continue
            }

            if trimmed.hasPrefix("```") {
                flushParagraph()
                var codeLines: [String] = []
                index += 1
                while index < lines.count {
                    let codeLine = lines[index]
                    if codeLine.trimmingCharacters(in: .whitespacesAndNewlines).hasPrefix("```") {
                        break
                    }
                    codeLines.append(codeLine)
                    index += 1
                }
                blocks.append(.code(codeLines.joined(separator: "\n")))
                index += 1
                continue
            }

            if trimmed == "$$" || trimmed.hasPrefix("$$") {
                flushParagraph()
                let startsAndEndsInline = trimmed.hasPrefix("$$") && trimmed.hasSuffix("$$") && trimmed.count > 4
                if startsAndEndsInline {
                    blocks.append(.formula(String(trimmed.dropFirst(2).dropLast(2))))
                    index += 1
                    continue
                }
                var formulaLines: [String] = []
                if trimmed.count > 2 {
                    formulaLines.append(String(trimmed.dropFirst(2)))
                }
                index += 1
                while index < lines.count {
                    let formulaLine = lines[index].trimmingCharacters(in: .whitespacesAndNewlines)
                    if formulaLine.hasSuffix("$$") {
                        formulaLines.append(String(formulaLine.dropLast(2)))
                        break
                    }
                    formulaLines.append(lines[index])
                    index += 1
                }
                blocks.append(.formula(formulaLines.joined(separator: "\n")))
                index += 1
                continue
            }

            if trimmed == "\\[" || trimmed.hasPrefix("\\[") {
                flushParagraph()
                var formulaLines: [String] = []
                if trimmed.count > 2 {
                    formulaLines.append(String(trimmed.dropFirst(2)))
                }
                index += 1
                while index < lines.count {
                    let formulaLine = lines[index].trimmingCharacters(in: .whitespacesAndNewlines)
                    if formulaLine.hasSuffix("\\]") {
                        formulaLines.append(String(formulaLine.dropLast(2)))
                        break
                    }
                    formulaLines.append(lines[index])
                    index += 1
                }
                blocks.append(.formula(formulaLines.joined(separator: "\n")))
                index += 1
                continue
            }

            if isHorizontalRule(trimmed) {
                flushParagraph()
                blocks.append(.rule)
                index += 1
                continue
            }

            if let heading = parseHeading(trimmed) {
                flushParagraph()
                blocks.append(.heading(level: heading.level, text: heading.text))
                index += 1
                continue
            }

            if let ordered = parseOrderedItem(trimmed) {
                flushParagraph()
                blocks.append(.ordered(number: ordered.number, text: ordered.text))
                index += 1
                continue
            }

            if let bullet = parseBullet(trimmed) {
                flushParagraph()
                blocks.append(.bullet(bullet))
                index += 1
                continue
            }

            if trimmed.hasPrefix(">") {
                flushParagraph()
                blocks.append(.quote(String(trimmed.dropFirst()).trimmingCharacters(in: .whitespacesAndNewlines)))
                index += 1
                continue
            }

            paragraph.append(trimmed)
            index += 1
        }

        flushParagraph()
        return blocks
    }

    private static func parseHeading(_ line: String) -> (level: Int, text: String)? {
        let level = line.prefix(while: { $0 == "#" }).count
        guard (1...6).contains(level), line.dropFirst(level).first == " " else { return nil }
        return (level, String(line.dropFirst(level)).trimmingCharacters(in: .whitespacesAndNewlines))
    }

    private static func parseBullet(_ line: String) -> String? {
        for marker in ["- ", "* ", "• "] where line.hasPrefix(marker) {
            return String(line.dropFirst(marker.count)).trimmingCharacters(in: .whitespacesAndNewlines)
        }
        return nil
    }

    private static func parseOrderedItem(_ line: String) -> (number: String, text: String)? {
        guard let dot = line.firstIndex(of: ".") else { return nil }
        let number = String(line[..<dot])
        guard !number.isEmpty, number.allSatisfy(\.isNumber) else { return nil }
        let afterDot = line[line.index(after: dot)...]
        guard afterDot.first == " " else { return nil }
        return (number, String(afterDot).trimmingCharacters(in: .whitespacesAndNewlines))
    }

    private static func isHorizontalRule(_ line: String) -> Bool {
        let compact = line.replacingOccurrences(of: " ", with: "")
        guard compact.count >= 3 else { return false }
        return compact.allSatisfy { $0 == "-" } || compact.allSatisfy { $0 == "*" } || compact.allSatisfy { $0 == "_" }
    }
}

extension String {
    func replacingInlineFormulaDelimitersWithCode() -> String {
        var output = ""
        var index = startIndex
        while index < endIndex {
            if self[index] == "$", nextIndex(after: index).map({ self[$0] != "$" }) == true,
               let end = findInlineDollarEnd(after: index) {
                let formula = String(self[self.index(after: index)..<end]).sanitizedInlineFormula
                output += "`\(formula)`"
                index = self.index(after: end)
                continue
            }

            if startsWith("\\(", at: index), let end = range(of: "\\)", range: self.index(index, offsetBy: 2)..<endIndex) {
                let formula = String(self[self.index(index, offsetBy: 2)..<end.lowerBound]).sanitizedInlineFormula
                output += "`\(formula)`"
                index = end.upperBound
                continue
            }

            output.append(self[index])
            index = self.index(after: index)
        }
        return output
    }

    func strippingInlineFormulaDelimiters() -> String {
        replacingInlineFormulaDelimitersWithCode()
            .replacingOccurrences(of: "`", with: "")
    }

    private var sanitizedInlineFormula: String {
        replacingOccurrences(of: "`", with: "'")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func nextIndex(after index: String.Index) -> String.Index? {
        let next = self.index(after: index)
        return next < endIndex ? next : nil
    }

    private func startsWith(_ prefix: String, at index: String.Index) -> Bool {
        guard let end = self.index(index, offsetBy: prefix.count, limitedBy: endIndex) else { return false }
        return self[index..<end] == prefix[...]
    }

    private func findInlineDollarEnd(after start: String.Index) -> String.Index? {
        var index = self.index(after: start)
        while index < endIndex {
            if self[index] == "$" {
                let previous = self.index(before: index)
                if self[previous] != "\\" {
                    return index
                }
            }
            index = self.index(after: index)
        }
        return nil
    }
}

struct PaperDetailActionPanel: View {
    @Environment(\.modelContext) private var modelContext
    @EnvironmentObject private var library: LibraryViewModel
    @EnvironmentObject private var settings: AppSettings
    let paper: PaperRecord
    let pdfError: String
    let openReader: () -> Void
    @State private var cachedPDF: CachedPaperPDF?

    private let columns = [GridItem(.adaptive(minimum: 132), spacing: AppTheme.Spacing.sm)]

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            LazyVGrid(columns: columns, alignment: .leading, spacing: AppTheme.Spacing.sm) {
                Button {
                    library.toggleFavorite(paper, context: modelContext)
                } label: {
                    Label(paper.isFavorite ? "已收藏" : "收藏", systemImage: paper.isFavorite ? "bookmark.fill" : "bookmark")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)

                Button {
                    library.completeMissingInsights(for: paper, context: modelContext, settings: settings)
                } label: {
                    Label(paper.hasFullInsightPack ? "刷新三项" : "补全缺失", systemImage: "sparkles")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)

                Button(action: openReader) {
                    Label("阅读 PDF", systemImage: "doc.richtext")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .disabled(paper.pdfURL.isEmpty)

                Button {
                    Task {
                        cachedPDF = try? await library.preparePDF(for: paper)
                    }
                } label: {
                    Label(cachedPDF == nil ? "离线缓存" : "已缓存", systemImage: cachedPDF == nil ? "tray.and.arrow.down" : "externaldrive.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .disabled(paper.pdfURL.isEmpty)
            }

            if let cachedPDF {
                Label("PDF \(cachedPDF.bytes.formattedBytes)，可离线阅读", systemImage: "checkmark.seal.fill")
                    .font(AppTheme.Typography.footnoteEmphasis)
                    .foregroundStyle(AppTheme.ColorToken.success)
            }
            if !pdfError.isEmpty {
                Text(pdfError)
                    .font(AppTheme.Typography.footnote)
                    .foregroundStyle(AppTheme.ColorToken.danger)
            }
        }
        .forestCard()
        .task {
            cachedPDF = library.cachedPDF(for: paper)
        }
    }
}

struct NativeTranslationButton: View {
    let text: String
    @State private var showingTranslation = false

    var body: some View {
        #if canImport(Translation)
        if #available(iOS 17.4, *), !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            Button {
                showingTranslation = true
            } label: {
                Image(systemName: "translate")
                    .stableIconButtonStyle()
            }
            .accessibilityLabel("系统翻译")
            .translationPresentation(isPresented: $showingTranslation, text: text)
        } else {
            EmptyView()
        }
        #else
        EmptyView()
        #endif
    }
}

struct PDFReaderItem: Identifiable {
    var id: String { file.id }
    let paperTitle: String
    let file: CachedPaperPDF
}

struct PDFReaderSheet: View {
    @Environment(\.openURL) private var openURL
    let item: PDFReaderItem

    var body: some View {
        NavigationStack {
            Group {
                if PDFDocument(url: item.file.url) == nil {
                    PDFUnavailableView()
                } else {
                    PDFKitReader(url: item.file.url)
                        .ignoresSafeArea(edges: .bottom)
                }
            }
            .navigationTitle("PDF 阅读")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    ShareLink(item: item.file.url) {
                        Image(systemName: "square.and.arrow.up")
                    }
                    .accessibilityLabel("分享 PDF")
                    if let source = URL(string: item.file.sourceURL) {
                        Button {
                            openURL(source)
                        } label: {
                            Image(systemName: "safari")
                        }
                        .accessibilityLabel("在浏览器打开 PDF")
                    }
                }
            }
        }
    }
}

struct PDFUnavailableView: View {
    var body: some View {
        VStack(spacing: AppTheme.Spacing.md) {
            Image(systemName: "doc.badge.exclamationmark")
                .font(.system(size: 42))
                .foregroundStyle(AppTheme.ColorToken.warning)
            Text("PDF 暂时无法加载")
                .font(AppTheme.Typography.cardTitle)
                .foregroundStyle(AppTheme.ColorToken.ink)
            Text("缓存文件不是可读取的 PDF，返回详情页后重新缓存即可。")
                .font(AppTheme.Typography.label)
                .foregroundStyle(AppTheme.ColorToken.mutedInk)
                .multilineTextAlignment(.center)
        }
        .padding(AppTheme.Spacing.xl)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AppTheme.ColorToken.paper)
    }
}

struct PDFKitReader: UIViewRepresentable {
    let url: URL

    func makeUIView(context: Context) -> PDFView {
        let view = PDFView()
        view.autoScales = true
        view.displayMode = .singlePageContinuous
        view.displayDirection = .vertical
        view.backgroundColor = UIColor(AppTheme.ColorToken.paper)
        view.document = PDFDocument(url: url)
        return view
    }

    func updateUIView(_ uiView: PDFView, context: Context) {
        if uiView.document?.documentURL != url {
            uiView.document = PDFDocument(url: url)
        }
    }
}

struct FigurePagesView: View {
    let paper: PaperRecord

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            Label("PDF 关键页图册", systemImage: "photo.on.rectangle")
                .font(AppTheme.Typography.cardTitle)
                .foregroundStyle(AppTheme.ColorToken.ink)
            if paper.figurePages.isEmpty {
                Text("生成全文总结后，app 会记录 PDF 关键页，方便回到原文检查图表。")
                    .font(AppTheme.Typography.label)
                    .foregroundStyle(AppTheme.ColorToken.mutedInk)
            } else {
                ForEach(paper.figurePages) { figure in
                    HStack(spacing: AppTheme.Spacing.md) {
                        ZStack {
                            RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous)
                                .fill(AppTheme.ColorToken.paperDeep)
                                .frame(width: 76, height: 92)
                            VStack {
                                Image(systemName: "doc.richtext")
                                    .foregroundStyle(AppTheme.ColorToken.arxivBlue)
                                Text("\(figure.page)")
                                    .font(AppTheme.Typography.metric)
                                    .foregroundStyle(AppTheme.ColorToken.ink)
                            }
                        }
                        VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                            Text(figure.label)
                                .font(AppTheme.Typography.label)
                                .foregroundStyle(AppTheme.ColorToken.ink)
                            Text(figure.reason)
                                .font(AppTheme.Typography.footnote)
                                .foregroundStyle(AppTheme.ColorToken.mutedInk)
                        }
                    }
                    .padding(AppTheme.Spacing.sm)
                    .background(AppTheme.ColorToken.paper.opacity(0.62), in: RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous))
                }
            }
        }
        .forestCard()
    }
}

struct EmptyPaperListState: View {
    let favoritesOnly: Bool

    var body: some View {
        VStack(spacing: AppTheme.Spacing.md) {
            Image(systemName: favoritesOnly ? "bookmark.circle" : "doc.text.magnifyingglass")
                .font(.system(size: 46))
                .foregroundStyle(AppTheme.ColorToken.canopy)
            Text(favoritesOnly ? "还没有收藏论文" : "当前批次没有论文")
                .font(AppTheme.Typography.cardTitle)
                .foregroundStyle(AppTheme.ColorToken.ink)
            Text(favoritesOnly ? "在论文卡片或详情页点收藏后，这里会形成你的阅读清单。" : "回到森林页点击抓取，或切换到其他 arXiv 公告批次。")
                .font(AppTheme.Typography.label)
                .foregroundStyle(AppTheme.ColorToken.mutedInk)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .forestCard(padding: AppTheme.Spacing.xxl)
    }
}

extension String {
    func summaryExcerpt(limit: Int) -> String {
        let clean = markdownPreviewText.components(separatedBy: .whitespacesAndNewlines).filter { !$0.isEmpty }.joined(separator: " ")
        if clean.count <= limit {
            return clean
        }
        return String(clean.prefix(limit)) + "..."
    }

    private var markdownPreviewText: String {
        let blocks = MarkdownBlockParser.parse(self)
        let extracted = blocks.compactMap { block -> String? in
            switch block {
            case .heading(_, let text):
                return text
            case .paragraph(let text), .bullet(let text), .quote(let text):
                return text
            case .ordered(_, let text):
                return text
            case .formula, .code, .rule:
                return nil
            }
        }
        let text = extracted.isEmpty ? self : extracted.joined(separator: " ")
        return text.strippingMarkdownPreviewSyntax()
    }

    private func strippingMarkdownPreviewSyntax() -> String {
        replacingInlineFormulaDelimitersWithCode()
            .replacingOccurrences(of: "`", with: "")
            .replacingOccurrences(of: #"(?m)^#{1,6}\s*"#, with: "", options: .regularExpression)
            .replacingOccurrences(of: #"\*\*([^*]+)\*\*"#, with: "$1", options: .regularExpression)
            .replacingOccurrences(of: #"__([^_]+)__"#, with: "$1", options: .regularExpression)
            .replacingOccurrences(of: #"\*([^*]+)\*"#, with: "$1", options: .regularExpression)
            .replacingOccurrences(of: #"_([^_]+)_"#, with: "$1", options: .regularExpression)
            .replacingOccurrences(of: #"\[([^\]]+)\]\([^)]+\)"#, with: "$1", options: .regularExpression)
            .replacingOccurrences(of: #"(?m)^\s*[-*]\s+"#, with: "", options: .regularExpression)
            .replacingOccurrences(of: #"(?m)^\s*\d+\.\s+"#, with: "", options: .regularExpression)
            .replacingOccurrences(of: #"(?m)^\s*[-*_]{3,}\s*$"#, with: "", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
