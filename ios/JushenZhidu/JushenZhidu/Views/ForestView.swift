import SwiftData
import SwiftUI

struct ForestView: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.modelContext) private var modelContext
    @EnvironmentObject private var library: LibraryViewModel
    @EnvironmentObject private var settings: AppSettings
    @Query private var papers: [PaperRecord]
    @State private var selectedPaper: PaperRecord?
    @State private var focusedPaper: PaperRecord?
    @State private var expandedTopicKeys: Set<String> = []
    @State private var forceRefresh = false

    private var visiblePapers: [PaperRecord] {
        library.filteredPapers(papers)
    }

    private var tabBarClearance: CGFloat {
        78
    }

    var body: some View {
        NavigationStack {
            ZStack {
                ForestBackground()
                ScrollView {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                        BatchHeaderView(
                            title: "论文森林",
                            subtitle: "arXiv 公告批次 \(library.selectedBatchDayText)",
                            paperCount: visiblePapers.count,
                            matchedCount: library.filteredPapers(papers).count,
                            onPrevious: { library.previousBatchDay() },
                            onNext: { library.nextBatchDay() },
                            onFetch: { library.fetchCurrentBatch(context: modelContext, forceRefresh: forceRefresh, settings: settings) }
                        )
                        .accessibilityIdentifier("forest.batchHeader")

                        ForestControls(forceRefresh: $forceRefresh)

                        ForestMapView(
                            papers: visiblePapers,
                            focusedPaper: $focusedPaper,
                            expandedTopicKeys: $expandedTopicKeys
                        )
                        .accessibilityIdentifier("forest.map")
                    }
                    .padding(AppTheme.Spacing.lg)
                }
            }
            .overlay(alignment: .bottom) {
                bottomOverlay
            }
            .animation(reduceMotion ? nil : AppTheme.Motion.drawer, value: selectedPaper?.arxivId)
            .navigationTitle("具身智读")
            .navigationBarTitleDisplayMode(.inline)
            .fullScreenCover(item: $selectedPaper) { paper in
                ForestPaperDetailFullScreen(paper: paper)
            }
        }
    }

    @ViewBuilder
    private var bottomOverlay: some View {
        floatingPaperPanel
    }

    @ViewBuilder
    private var floatingPaperPanel: some View {
        if let focusedPaper {
            ForestPaperDetailLauncher(
                paper: focusedPaper,
                openDetail: {
                    withAnimation(AppTheme.Motion.drawer) {
                        selectedPaper = focusedPaper
                    }
                }
            )
            .padding(.horizontal, AppTheme.Spacing.lg)
            .padding(.bottom, tabBarClearance)
            .transition(.asymmetric(
                insertion: .scale(scale: 0.90, anchor: .bottom).combined(with: .opacity),
                removal: .scale(scale: 0.96, anchor: .bottom).combined(with: .opacity)
            ))
            .zIndex(10)
        }
    }

}

struct ForestPaperDetailFullScreen: View {
    @Environment(\.dismiss) private var dismiss
    let paper: PaperRecord

    var body: some View {
        NavigationStack {
            PaperDetailView(paper: paper)
                .toolbar {
                    ToolbarItem(placement: .topBarLeading) {
                        Button {
                            dismiss()
                        } label: {
                            Image(systemName: "xmark")
                                .stableIconButtonStyle()
                        }
                        .buttonStyle(.forestPress)
                        .accessibilityLabel("关闭论文详情")
                    }
                }
        }
    }
}

struct BatchHeaderView: View {
    let title: String
    let subtitle: String
    let paperCount: Int
    let matchedCount: Int
    let onPrevious: () -> Void
    let onNext: () -> Void
    let onFetch: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
                BrandMark()
                VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                    Text(title)
                        .font(AppTheme.Typography.display)
                        .foregroundStyle(AppTheme.ColorToken.ink)
                        .minimumScaleFactor(0.75)
                    Text(subtitle)
                        .font(AppTheme.Typography.label)
                        .foregroundStyle(AppTheme.ColorToken.mutedInk)
                }
                Spacer()
                VStack(alignment: .trailing, spacing: AppTheme.Spacing.xs) {
                    Text("\(paperCount)")
                        .font(AppTheme.Typography.metric)
                        .foregroundStyle(AppTheme.ColorToken.mossDark)
                    Text("当前可见")
                        .font(AppTheme.Typography.caption)
                        .foregroundStyle(AppTheme.ColorToken.mutedInk)
                }
            }

            HStack(spacing: AppTheme.Spacing.sm) {
                Button(action: onPrevious) {
                    Image(systemName: "chevron.left")
                        .stableIconButtonStyle()
                }
                .accessibilityLabel("前一批")

                Button(action: onNext) {
                    Image(systemName: "chevron.right")
                        .stableIconButtonStyle()
                }
                .accessibilityLabel("后一批")

                Spacer()

                BatchMetricPill(value: "\(matchedCount)", label: "命中", systemImage: "scope")

                Button(action: onFetch) {
                    Label("抓取", systemImage: "arrow.triangle.2.circlepath")
                        .font(AppTheme.Typography.action)
                        .padding(.horizontal, AppTheme.Spacing.lg)
                        .padding(.vertical, AppTheme.Spacing.md)
                        .foregroundStyle(.white)
                        .background(AppTheme.ColorToken.warmAction, in: RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous))
                }
                .accessibilityIdentifier("action.fetch")
            }
        }
        .forestCard()
    }
}

struct BatchMetricPill: View {
    let value: String
    let label: String
    let systemImage: String

    var body: some View {
        Label {
            HStack(spacing: AppTheme.Spacing.xs) {
                Text(value)
                    .font(AppTheme.Typography.monoCaption)
                Text(label)
                    .font(AppTheme.Typography.caption)
            }
        } icon: {
            Image(systemName: systemImage)
                .font(AppTheme.Typography.captionStrong)
        }
        .foregroundStyle(AppTheme.ColorToken.mossDark)
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.sm)
        .background(AppTheme.ColorToken.paperDeep, in: Capsule())
    }
}

struct ForestControls: View {
    @EnvironmentObject private var library: LibraryViewModel
    @Binding var forceRefresh: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack(spacing: AppTheme.Spacing.md) {
                Label("筛选", systemImage: "line.3.horizontal.decrease.circle")
                    .font(AppTheme.Typography.sectionTitle)
                    .foregroundStyle(AppTheme.ColorToken.ink)
                Spacer()
                Toggle(isOn: $forceRefresh) {
                    Text("跳过缓存")
                }
                .font(AppTheme.Typography.footnoteEmphasis)
                .toggleStyle(.switch)
            }

            ResearchSearchField(text: $library.searchText, placeholder: "搜索标题、作者、关键词")

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: AppTheme.Spacing.sm) {
                    TopicFilterChip(key: "all", label: "全部", systemImage: "square.grid.2x2")
                    ForEach(ResearchTopic.filterTopics) { topic in
                        TopicFilterChip(key: topic.key, label: topic.labelZh, systemImage: topic.key == "foundation" ? "sparkles" : "leaf")
                    }
                }
                .padding(.vertical, 1)
            }
        }
        .forestCard()
    }
}

struct ResearchSearchField: View {
    @Binding var text: String
    let placeholder: String

    var body: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: "magnifyingglass")
                .font(AppTheme.Typography.label)
                .foregroundStyle(AppTheme.ColorToken.mutedInk)
                .frame(width: 22)
            TextField("", text: $text, prompt: Text(placeholder).foregroundStyle(AppTheme.ColorToken.mutedInk))
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .foregroundStyle(AppTheme.ColorToken.ink)
        }
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.ColorToken.fieldBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous)
                .stroke(AppTheme.ColorToken.lineSoft, lineWidth: 1)
        }
    }
}

struct TopicFilterChip: View {
    @EnvironmentObject private var library: LibraryViewModel
    let key: String
    let label: String
    let systemImage: String

    private var selected: Bool {
        library.selectedTopicKey == key
    }

    var body: some View {
        Button {
            library.selectedTopicKey = key
        } label: {
            Label(label, systemImage: systemImage)
                .font(AppTheme.Typography.caption)
                .padding(.horizontal, AppTheme.Spacing.md)
                .padding(.vertical, AppTheme.Spacing.sm)
                .foregroundStyle(selected ? Color.white : AppTheme.ColorToken.mossDark)
                .background(selected ? AppTheme.ColorToken.canopy : AppTheme.ColorToken.paperDeep, in: Capsule())
        }
    }
}

struct ForestMapView: View {
    let papers: [PaperRecord]
    @Binding var focusedPaper: PaperRecord?
    @Binding var expandedTopicKeys: Set<String>

    private var grouped: [(topic: ResearchTopic, papers: [PaperRecord])] {
        ResearchTopic.filterTopics.compactMap { topic in
            let rows = papers.filter { $0.topicKey == topic.key }
            return rows.isEmpty ? nil : (topic, rows)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
            HStack {
                Label("森林地图", systemImage: "map")
                    .font(AppTheme.Typography.sectionTitle)
                    .foregroundStyle(AppTheme.ColorToken.ink)
                Spacer()
                Label("\(papers.filter(\.hasFullInsightPack).count) 完整", systemImage: "checkmark.seal.fill")
                    .font(AppTheme.Typography.captionStrong)
                    .foregroundStyle(AppTheme.ColorToken.success)
            }

            ForestMapStatusStrip(papers: papers)

            if papers.isEmpty {
                EmptyForestState()
            } else {
                VStack(spacing: AppTheme.Spacing.lg) {
                    ForEach(grouped, id: \.topic.key) { group in
                        ForestGroveView(
                            topic: group.topic,
                            papers: group.papers,
                            focusedPaper: $focusedPaper,
                            isExpanded: expandedTopicKeys.contains(group.topic.key),
                            toggleExpanded: { toggleExpanded(group.topic.key) }
                        )
                    }
                }
            }
        }
        .padding(AppTheme.Spacing.lg)
        .background(ForestMapSurface())
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous)
                .stroke(AppTheme.ColorToken.mossDark, lineWidth: 2)
        }
    }

    private func toggleExpanded(_ key: String) {
        var next = expandedTopicKeys
        if next.contains(key) {
            next.remove(key)
            if focusedPaper?.topicKey == key {
                focusedPaper = nil
            }
        } else {
            next.insert(key)
        }
        withAnimation(AppTheme.Motion.panel) {
            expandedTopicKeys = next
        }
    }
}

struct ForestPaperDetailLauncher: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let paper: PaperRecord
    let openDetail: () -> Void

    var body: some View {
        Button(action: openDetail) {
            HStack(spacing: AppTheme.Spacing.md) {
                PaperForestThumbnail(paper: paper, size: 44)
                    .overlay(alignment: .bottomTrailing) {
                        if paper.hasFullInsightPack {
                            Image(systemName: "checkmark.seal.fill")
                                .font(AppTheme.Typography.captionSmallStrong)
                                .foregroundStyle(AppTheme.ColorToken.success)
                                .padding(3)
                                .background(AppTheme.ColorToken.paper.opacity(0.92), in: Circle())
                                .offset(x: 3, y: 3)
                        }
                    }

                VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                    Text(paper.title)
                        .font(AppTheme.Typography.englishFootnote)
                        .foregroundStyle(Color.white)
                        .lineLimit(1)
                        .truncationMode(.tail)
                    HStack(spacing: AppTheme.Spacing.xs) {
                        Text(paper.topic.labelZh)
                        Text(String(format: "%.1f", paper.relevanceScore))
                        Text("\(paper.insightCompletionCount)/3")
                    }
                    .font(AppTheme.Typography.englishFootnote)
                    .foregroundStyle(Color.white.opacity(0.72))
                }

                Image(systemName: "chevron.up")
                    .font(AppTheme.Typography.captionStrong)
                    .foregroundStyle(Color.white.opacity(0.88))
                    .frame(width: 30, height: 30)
                    .background(Color.white.opacity(0.14), in: Circle())
            }
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, AppTheme.Spacing.sm)
            .frame(maxWidth: .infinity)
            .background(launcherBackground, in: Capsule())
            .overlay {
                Capsule()
                    .stroke(Color.white.opacity(0.18), lineWidth: 1)
            }
            .shadow(color: AppTheme.ColorToken.canopy.opacity(0.34), radius: 18, x: 0, y: 10)
        }
        .buttonStyle(.forestPress)
        .accessibilityLabel("打开论文详细阅读：\(paper.title)")
        .animation(reduceMotion ? nil : AppTheme.Motion.panel, value: paper.arxivId)
    }

    private var launcherBackground: LinearGradient {
        LinearGradient(
            colors: [
                AppTheme.ColorToken.canopy.opacity(0.98),
                AppTheme.ColorToken.mossDark.opacity(0.96)
            ],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }
}

struct InsightTaskButton: View {
    let kind: InsightKind
    let paper: PaperRecord
    let activeTask: TaskActivity?
    var compact = false
    let action: () -> Void

    private var state: InsightButtonState {
        if activeTask?.paperId == paper.arxivId, activeTask?.insightKind == kind {
            if activeTask?.stage == "failed" {
                return .failed
            }
            if activeTask?.isTerminal == false {
                return .running
            }
        }
        return paper.hasInsight(kind) ? .done : .idle
    }

    var body: some View {
        Button(action: action) {
            HStack(spacing: AppTheme.Spacing.xs) {
                statusIcon
                    .frame(width: compact ? 13 : 16, height: compact ? 13 : 16)
                Text(compact ? compactLabel : kind.label)
                    .lineLimit(1)
                    .minimumScaleFactor(0.82)
            }
            .font(compact ? AppTheme.Typography.captionSmallStrong : AppTheme.Typography.chineseCaption)
            .foregroundStyle(foregroundColor)
            .frame(width: compact ? 44 : nil, height: compact ? 30 : nil)
            .frame(maxWidth: compact ? nil : .infinity)
            .padding(.vertical, compact ? 0 : AppTheme.Spacing.sm)
            .background(backgroundColor, in: RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous)
                    .stroke(borderColor, lineWidth: state == .running ? 2 : 1)
            }
            .scaleEffect(state == .running ? 1.015 : 1)
        }
        .buttonStyle(.forestPress)
        .disabled(isPaperTaskRunning)
        .opacity(isPaperTaskRunning && state != .running ? 0.72 : 1)
        .animation(AppTheme.Motion.control, value: state)
        .accessibilityLabel("\(kind.label)\(accessibilityState)")
    }

    @ViewBuilder
    private var statusIcon: some View {
        if state == .running {
            ProgressView()
                .controlSize(.mini)
                .tint(AppTheme.ColorToken.warmAction)
        } else {
            Image(systemName: iconName)
                .font(AppTheme.Typography.captionSmallStrong)
        }
    }

    private var iconName: String {
        switch state {
        case .idle:
            return kind.systemImage
        case .running:
            return "hourglass"
        case .done:
            return "checkmark.circle.fill"
        case .failed:
            return "exclamationmark.circle.fill"
        }
    }

    private var compactLabel: String {
        switch kind {
        case .translation:
            return "译"
        case .summary:
            return "速"
        case .fullText:
            return "深"
        }
    }

    private var foregroundColor: Color {
        switch state {
        case .idle:
            return AppTheme.ColorToken.mossDark
        case .running:
            return AppTheme.ColorToken.warmAction
        case .done:
            return AppTheme.ColorToken.success
        case .failed:
            return AppTheme.ColorToken.danger
        }
    }

    private var backgroundColor: Color {
        switch state {
        case .idle:
            return AppTheme.ColorToken.vellum.opacity(0.76)
        case .running:
            return AppTheme.ColorToken.paperDeep.opacity(0.86)
        case .done:
            return AppTheme.ColorToken.mist.opacity(0.86)
        case .failed:
            return AppTheme.ColorToken.vellum.opacity(0.88)
        }
    }

    private var borderColor: Color {
        switch state {
        case .idle:
            return AppTheme.ColorToken.lineSoft
        case .running:
            return AppTheme.ColorToken.warmAction
        case .done:
            return AppTheme.ColorToken.success.opacity(0.55)
        case .failed:
            return AppTheme.ColorToken.danger.opacity(0.65)
        }
    }

    private var accessibilityState: String {
        switch state {
        case .idle:
            return "未生成"
        case .running:
            return "生成中"
        case .done:
            return "已完成"
        case .failed:
            return "失败，可重试"
        }
    }

    private var isPaperTaskRunning: Bool {
        activeTask?.paperId == paper.arxivId && activeTask?.isTerminal == false
    }
}

private enum InsightButtonState {
    case idle
    case running
    case done
    case failed
}

struct FloatingInsightSummary: View {
    let paper: PaperRecord

    var body: some View {
        HStack(spacing: AppTheme.Spacing.xs) {
            InsightStatusView(paper: paper)
        }
        .padding(.horizontal, AppTheme.Spacing.sm)
        .padding(.vertical, AppTheme.Spacing.xs)
        .background(AppTheme.ColorToken.vellum.opacity(0.76), in: Capsule())
        .accessibilityLabel("智能阅读完成 \(paper.insightCompletionCount) 项，共 3 项")
    }
}

struct ForestMapStatusStrip: View {
    let papers: [PaperRecord]

    var body: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 112), spacing: AppTheme.Spacing.sm)], spacing: AppTheme.Spacing.sm) {
            ForestMapMetric(value: "\(papers.count)", label: "论文树", systemImage: "tree.fill", tint: AppTheme.ColorToken.mossDark)
            ForestMapMetric(value: "\(papers.filter(\.isFavorite).count)", label: "收藏", systemImage: "bookmark.fill", tint: AppTheme.ColorToken.warmAction)
            ForestMapMetric(value: "\(papers.filter(\.hasFullInsightPack).count)", label: "AI 完成", systemImage: "checkmark.seal.fill", tint: AppTheme.ColorToken.success)
        }
    }
}

struct ForestMapMetric: View {
    let value: String
    let label: String
    let systemImage: String
    let tint: Color

    var body: some View {
        HStack(spacing: AppTheme.Spacing.sm) {
            Image(systemName: systemImage)
                .font(AppTheme.Typography.captionStrong)
                .foregroundStyle(tint)
                .frame(width: 20)
            VStack(alignment: .leading, spacing: 1) {
                Text(value)
                    .font(AppTheme.Typography.monoCaption)
                    .foregroundStyle(AppTheme.ColorToken.ink)
                Text(label)
                    .font(AppTheme.Typography.captionSmall)
                    .foregroundStyle(AppTheme.ColorToken.mutedInk)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, AppTheme.Spacing.sm)
        .padding(.vertical, AppTheme.Spacing.xs)
        .background(AppTheme.ColorToken.paper.opacity(0.72), in: RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous))
    }
}

struct ForestMapSurface: View {
    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous)
                .fill(LinearGradient(colors: [AppTheme.ColorToken.mapLight, AppTheme.ColorToken.mapDeep], startPoint: .top, endPoint: .bottom))
            Image("ForestTerrainMoss")
                .resizable(resizingMode: .tile)
                .interpolation(.none)
                .opacity(0.16)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous))
        }
    }
}

struct ForestGroveView: View {
    let topic: ResearchTopic
    let papers: [PaperRecord]
    @Binding var focusedPaper: PaperRecord?
    let isExpanded: Bool
    let toggleExpanded: () -> Void

    private let columns = [GridItem(.adaptive(minimum: 92, maximum: 112), spacing: 12)]

    private var displayedPapers: [PaperRecord] {
        isExpanded ? papers : Array(papers.prefix(3))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            HStack(spacing: AppTheme.Spacing.sm) {
                VStack(alignment: .leading, spacing: 1) {
                    Text(topic.labelZh)
                        .font(AppTheme.Typography.sectionTitle)
                    Text(topic.label)
                        .font(AppTheme.Typography.caption)
                        .foregroundStyle(AppTheme.ColorToken.mossMuted)
                }
                Spacer()
                ForestGroveLegend(papers: papers)
                Text("\(papers.count)")
                    .font(AppTheme.Typography.number)
                    .padding(.horizontal, AppTheme.Spacing.sm)
                    .padding(.vertical, AppTheme.Spacing.xs)
                    .background(AppTheme.ColorToken.paperDeep, in: Capsule())
                Button(action: toggleExpanded) {
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .stableIconButtonStyle()
                }
                .accessibilityLabel(isExpanded ? "折叠\(topic.labelZh)" : "展开\(topic.labelZh)")
            }
            .foregroundStyle(AppTheme.ColorToken.ink)

            if let leadPaper = papers.first {
                GroveHeadlinePaper(paper: leadPaper) {
                    withAnimation(AppTheme.Motion.panel) {
                        focusedPaper = leadPaper
                    }
                }
            }

            LazyVGrid(columns: columns, spacing: 10) {
                ForEach(Array(displayedPapers.enumerated()), id: \.element.arxivId) { index, paper in
                    TreeTile(
                        paper: paper,
                        rank: index + 1,
                        isFocused: focusedPaper?.arxivId == paper.arxivId
                    ) {
                        withAnimation(AppTheme.Motion.panel) {
                            focusedPaper = paper
                        }
                    }
                }
            }

            if !isExpanded && papers.count > displayedPapers.count {
                Button(action: toggleExpanded) {
                    Label("展开其余 \(papers.count - displayedPapers.count) 篇", systemImage: "chevron.down.circle")
                        .font(AppTheme.Typography.chineseLabel)
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .tint(AppTheme.ColorToken.mossDark)
            }

        }
        .padding(AppTheme.Spacing.md)
        .background {
            ZStack {
                AppTheme.ColorToken.paper.opacity(0.34)
                LinearGradient(
                    colors: [AppTheme.ColorToken.paper.opacity(0.24), AppTheme.ColorToken.canopy.opacity(0.16)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )
            }
            .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous))
        }
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous)
                .stroke(AppTheme.ColorToken.paper.opacity(0.58), lineWidth: 1)
        }
    }
}

struct GroveHeadlinePaper: View {
    let paper: PaperRecord
    let focus: () -> Void

    var body: some View {
        Button(action: focus) {
            HStack(alignment: .top, spacing: AppTheme.Spacing.sm) {
                Image(systemName: "doc.text.magnifyingglass")
                    .font(AppTheme.Typography.captionStrong)
                    .foregroundStyle(AppTheme.ColorToken.arxivBlue)
                    .frame(width: 24, height: 24)
                    .background(AppTheme.ColorToken.vellum.opacity(0.82), in: Circle())

                VStack(alignment: .leading, spacing: 3) {
                    Text("代表论文")
                        .font(AppTheme.Typography.chineseCaption)
                        .foregroundStyle(AppTheme.ColorToken.mossMuted)
                    Text(paper.title)
                        .font(AppTheme.Typography.englishFootnote)
                        .foregroundStyle(AppTheme.ColorToken.ink)
                        .lineLimit(2)
                        .multilineTextAlignment(.leading)
                    if !paper.translationTitle.isEmpty {
                        Text(paper.translationTitle)
                            .font(AppTheme.Typography.chineseCaption)
                            .foregroundStyle(AppTheme.ColorToken.arxivBlue)
                            .lineLimit(1)
                    }
                }

                Spacer(minLength: 0)
            }
            .padding(AppTheme.Spacing.sm)
            .background(AppTheme.ColorToken.vellum.opacity(0.76), in: RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous)
                    .stroke(AppTheme.ColorToken.lineSoft, lineWidth: 1)
            }
        }
        .buttonStyle(.forestPress)
        .accessibilityLabel("聚焦代表论文 \(paper.title)")
    }
}

struct ForestGroveLegend: View {
    let papers: [PaperRecord]

    var body: some View {
        HStack(spacing: AppTheme.Spacing.xs) {
            ForestGroveLegendDot(color: AppTheme.ColorToken.paperDeep, label: "\(papers.filter { $0.plantTier == .sapling }.count)")
            ForestGroveLegendDot(color: AppTheme.ColorToken.warmAction, label: "\(papers.filter(\.isFavorite).count)")
            ForestGroveLegendDot(color: AppTheme.ColorToken.success, label: "\(papers.filter(\.hasFullInsightPack).count)")
        }
        .accessibilityHidden(true)
    }
}

struct ForestGroveLegendDot: View {
    let color: Color
    let label: String

    var body: some View {
        HStack(spacing: 3) {
            Circle()
                .fill(color)
                .frame(width: 6, height: 6)
            Text(label)
                .font(AppTheme.Typography.metricTiny)
                .foregroundStyle(AppTheme.ColorToken.mutedInk)
        }
    }
}

struct TreeTile: View {
    let paper: PaperRecord
    let rank: Int
    let isFocused: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            ZStack {
                RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous)
                    .fill(tileGradient)
                    .overlay(alignment: .bottom) {
                        Ellipse()
                            .fill(AppTheme.ColorToken.canopy.opacity(0.22))
                            .frame(width: 58, height: 15)
                            .blur(radius: 1)
                            .offset(y: -12)
                    }

                AnimatedTreeSprite(
                    assetName: paper.forestSpriteAssetName,
                    height: spriteHeight,
                    baseYOffset: paper.plantTier == .sapling ? 7 : 0,
                    seed: paper.arxivId,
                    isComplete: paper.hasFullInsightPack
                )

                VStack {
                    HStack(alignment: .top) {
                        Text("#\(rank)")
                            .font(AppTheme.Typography.metricTiny)
                            .foregroundStyle(AppTheme.ColorToken.mossDark)
                            .padding(.horizontal, AppTheme.Spacing.xs)
                            .padding(.vertical, 2)
                            .background(AppTheme.ColorToken.vellum.opacity(0.88), in: Capsule())
                        Spacer()
                        if paper.isFavorite {
                            Image(systemName: "bookmark.fill")
                                .font(AppTheme.Typography.captionSmallStrong)
                                .foregroundStyle(AppTheme.ColorToken.warmAction)
                                .frame(width: 20, height: 20)
                                .background(AppTheme.ColorToken.vellum.opacity(0.88), in: Circle())
                        }
                    }
                    Spacer()
                    HStack {
                        ForestInsightPips(paper: paper)
                        Spacer()
                        if paper.hasFullInsightPack {
                            Image(systemName: "checkmark.seal.fill")
                                .font(AppTheme.Typography.captionSmallStrong)
                                .foregroundStyle(AppTheme.ColorToken.success)
                                .padding(3)
                                .background(AppTheme.ColorToken.vellum.opacity(0.88), in: Circle())
                        }
                    }
                }
                .padding(6)
            }
            .frame(height: 96)
            .overlay {
                RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous)
                    .stroke(borderColor, lineWidth: isFocused ? 3 : paper.hasFullInsightPack ? 2 : 1)
            }
            .scaleEffect(isFocused ? 1.035 : 1)
            .shadow(color: isFocused ? AppTheme.ColorToken.arxivBlue.opacity(0.28) : Color.black.opacity(0.04), radius: isFocused ? 10 : 4, x: 0, y: isFocused ? 6 : 3)
            .animation(AppTheme.Motion.control, value: isFocused)
            .animation(AppTheme.Motion.status, value: paper.insightCompletionCount)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("\(paper.title)，\(paper.plantTier.label)")
        }
        .buttonStyle(.forestPress)
    }

    private var tileGradient: LinearGradient {
        LinearGradient(
            colors: [AppTheme.ColorToken.vellum.opacity(0.58), AppTheme.ColorToken.mapDeep.opacity(0.44)],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
    }

    private var spriteHeight: CGFloat {
        switch paper.plantTier {
        case .sapling:
            return 56
        case .young:
            return 68
        case .mature:
            return 76
        case .ancient:
            return 82
        }
    }

    private var borderColor: Color {
        if isFocused {
            return AppTheme.ColorToken.arxivBlue
        }
        if paper.hasFullInsightPack {
            return AppTheme.ColorToken.success
        }
        if paper.isFavorite {
            return AppTheme.ColorToken.warmAction
        }
        return AppTheme.ColorToken.paper.opacity(0.72)
    }
}

struct AnimatedTreeSprite: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let assetName: String
    let height: CGFloat
    let baseYOffset: CGFloat
    let seed: String
    let isComplete: Bool
    @State private var isMoving = false

    var body: some View {
        Image(assetName)
            .resizable()
            .interpolation(.none)
            .scaledToFit()
            .frame(height: height)
            .scaleEffect(x: treeScaleX, y: treeScaleY, anchor: .bottom)
            .rotationEffect(.degrees(treeRotation), anchor: .bottom)
            .offset(y: baseYOffset + treeYOffset)
            .shadow(color: Color.black.opacity(isComplete ? 0.26 : 0.14), radius: 5, x: 0, y: 4)
            .animation(reduceMotion ? nil : motionAnimation, value: isMoving)
            .onAppear {
                guard !reduceMotion else { return }
                isMoving = true
            }
            .onChange(of: reduceMotion) { _, newValue in
                isMoving = !newValue
            }
    }

    private var treeRotation: Double {
        guard !reduceMotion else { return 0 }
        return isMoving ? motionAmplitude : -motionAmplitude
    }

    private var treeScaleX: CGFloat {
        guard !reduceMotion else { return 1 }
        return isMoving ? 1.018 : 0.988
    }

    private var treeScaleY: CGFloat {
        guard !reduceMotion else { return 1 }
        return isMoving ? 0.992 : 1.012
    }

    private var treeYOffset: CGFloat {
        guard !reduceMotion else { return 0 }
        return isMoving ? -1.5 : 1
    }

    private var motionAnimation: Animation {
        .easeInOut(duration: motionDuration)
            .delay(motionDelay)
            .repeatForever(autoreverses: true)
    }

    private var motionAmplitude: Double {
        1.2 + Double(motionSeed % 7) * 0.16
    }

    private var motionDuration: Double {
        2.2 + Double(motionSeed % 5) * 0.28
    }

    private var motionDelay: Double {
        Double(motionSeed % 11) * 0.07
    }

    private var motionSeed: UInt64 {
        var hash: UInt64 = 14_695_981_039_346_656_037
        for byte in seed.utf8 {
            hash ^= UInt64(byte)
            hash &*= 1_099_511_628_211
        }
        return hash
    }
}

struct ForestInsightPips: View {
    let paper: PaperRecord

    var body: some View {
        HStack(spacing: 3) {
            ForestInsightPip(done: !paper.translationContent.isEmpty)
            ForestInsightPip(done: !paper.summaryContent.isEmpty)
            ForestInsightPip(done: !paper.fullTextSummaryContent.isEmpty)
        }
        .padding(.horizontal, 5)
        .padding(.vertical, 4)
        .background(AppTheme.ColorToken.vellum.opacity(0.72), in: Capsule())
        .accessibilityLabel("智能完成 \(paper.insightCompletionCount) 项")
    }
}

struct ForestInsightPip: View {
    let done: Bool

    var body: some View {
        Circle()
            .fill(done ? AppTheme.ColorToken.success : AppTheme.ColorToken.mossMuted.opacity(0.36))
            .frame(width: 5, height: 5)
    }
}

struct PaperForestThumbnail: View {
    let paper: PaperRecord
    var size: CGFloat = 68

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [
                            AppTheme.ColorToken.mapLight.opacity(0.92),
                            AppTheme.ColorToken.mist.opacity(0.74),
                            AppTheme.ColorToken.mapDeep.opacity(0.84)
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
            Image(paper.forestTerrainAssetName)
                .resizable(resizingMode: .tile)
                .interpolation(.none)
                .opacity(0.34)
                .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous))
            Circle()
                .fill(AppTheme.ColorToken.paper.opacity(0.28))
                .frame(width: size * 0.88, height: size * 0.88)
                .blur(radius: 4)
                .offset(y: -size * 0.08)
            Ellipse()
                .fill(AppTheme.ColorToken.canopy.opacity(0.18))
                .frame(width: size * 0.72, height: size * 0.16)
                .blur(radius: 1)
                .offset(y: size * 0.30)
            AnimatedTreeSprite(
                assetName: paper.forestSpriteAssetName,
                height: thumbnailSpriteHeight,
                baseYOffset: thumbnailYOffset,
                seed: "thumb-\(paper.arxivId)",
                isComplete: paper.hasFullInsightPack
            )
        }
        .frame(width: size, height: size)
        .clipShape(RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous)
                .stroke(paper.hasFullInsightPack ? AppTheme.ColorToken.success : AppTheme.ColorToken.lineSoft, lineWidth: paper.hasFullInsightPack ? 2 : 1)
        }
        .shadow(color: AppTheme.softShadow, radius: 8, x: 0, y: 5)
        .accessibilityHidden(true)
    }

    private var thumbnailSpriteHeight: CGFloat {
        switch paper.plantTier {
        case .sapling:
            return size * 0.72
        case .young:
            return size * 0.76
        case .mature:
            return size * 0.80
        case .ancient:
            return size * 0.84
        }
    }

    private var thumbnailYOffset: CGFloat {
        switch paper.plantTier {
        case .sapling:
            return size * 0.10
        case .young:
            return size * 0.06
        case .mature:
            return size * 0.03
        case .ancient:
            return size * 0.01
        }
    }
}

struct EmptyForestState: View {
    var body: some View {
        VStack(spacing: AppTheme.Spacing.md) {
            Image(systemName: "tree.circle")
                .font(.system(size: 48))
                .foregroundStyle(AppTheme.ColorToken.ink)
            Text("当前批次还没有树")
                .font(AppTheme.Typography.cardTitle)
                .foregroundStyle(AppTheme.ColorToken.ink)
            Text("点击“抓取”，app 会直接从 arXiv 官方 API 获取论文并在本地生成森林。")
                .font(AppTheme.Typography.label)
                .foregroundStyle(AppTheme.ColorToken.mutedInk)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(AppTheme.Spacing.xxl)
        .background(AppTheme.ColorToken.paper.opacity(0.62), in: RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous))
    }
}

struct ForestBackground: View {
    var body: some View {
        LinearGradient(
            colors: [AppTheme.ColorToken.paper, AppTheme.ColorToken.mapLight.opacity(0.36), AppTheme.ColorToken.paperDeep],
            startPoint: .topLeading,
            endPoint: .bottomTrailing
        )
        .ignoresSafeArea()
    }
}
