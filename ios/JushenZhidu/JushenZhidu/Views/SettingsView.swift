import SwiftData
import SwiftUI

struct SettingsView: View {
    @Environment(\.modelContext) private var modelContext
    @EnvironmentObject private var settings: AppSettings
    @EnvironmentObject private var library: LibraryViewModel
    @Query private var categories: [CategoryRecord]
    @Query private var groups: [KeywordGroupRecord]
    @Query private var rules: [KeywordRuleRecord]
    @State private var newCategory = ""
    @State private var newKeyword = ""

    var body: some View {
        NavigationStack {
            ZStack {
                ForestBackground()
                ScrollView {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.lg) {
                        SettingsHero()
                        FetchSettingsSection()
                        ModelSettingsSection()
                        NativeAISettingsSection()
                        CategorySettingsSection(categories: categories.sorted { $0.code < $1.code }, newCategory: $newCategory)
                        KeywordSettingsSection(groups: groups.sorted { $0.name < $1.name }, rules: rules, newKeyword: $newKeyword)
                        DataSettingsSection()
                    }
                    .padding(AppTheme.Spacing.lg)
                }
            }
            .navigationTitle("设置")
            .navigationBarTitleDisplayMode(.inline)
        }
    }

    @ViewBuilder
    private func FetchSettingsSection() -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            SectionTitle(systemImage: "tray.and.arrow.down", title: "arXiv 抓取")
            Stepper(value: Binding(get: {
                settings.fetchLimit
            }, set: { value in
                settings.fetchLimit = value
                settings.saveFetchLimit()
            }), in: 50...1_000, step: 50) {
                HStack {
                    VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                        Text("每批论文上限")
                            .font(AppTheme.Typography.label)
                            .foregroundStyle(AppTheme.ColorToken.ink)
                        Text("默认 200，增大后会按 arXiv 分页继续读取。")
                            .font(AppTheme.Typography.footnote)
                            .foregroundStyle(AppTheme.ColorToken.mutedInk)
                    }
                    Spacer(minLength: AppTheme.Spacing.md)
                    Text("\(settings.fetchLimit)")
                        .font(AppTheme.Typography.metricHeadline)
                        .foregroundStyle(AppTheme.ColorToken.mossDark)
                        .frame(minWidth: 56, alignment: .trailing)
                }
            }
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.ColorToken.paperDeep.opacity(0.64), in: RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous))
        }
        .forestCard()
    }

    @ViewBuilder
    private func ModelSettingsSection() -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            SectionTitle(systemImage: "sparkles", title: "智能模型")
            TextField("Base URL", text: $settings.baseURL)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .paperInputStyle()
            TextField("摘要模型", text: $settings.chatModel)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .paperInputStyle()
            HStack {
                Text("Temperature")
                Slider(value: $settings.temperature, in: 0...1, step: 0.05)
                Text(settings.temperature, format: .number.precision(.fractionLength(2)))
                    .font(AppTheme.Typography.metricSmall)
                    .frame(width: 42, alignment: .trailing)
            }
            Stepper("摘要输出上限 \(settings.maxTokensSingle)", value: $settings.maxTokensSingle, in: 400...4000, step: 100)
            Stepper("全文输出上限 \(settings.maxTokensFullText)", value: $settings.maxTokensFullText, in: 800...8000, step: 200)
            Stepper("PDF 文本上限 \(settings.fullTextMaxCharacters)", value: $settings.fullTextMaxCharacters, in: 10_000...120_000, step: 5_000)
            SecureField(settings.hasStoredAPIKey ? "已保存 API Key，输入新值可覆盖" : "API Key", text: $settings.apiKeyDraft)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .paperInputStyle()
            HStack {
                Button {
                    settings.save()
                } label: {
                    Label("保存设置", systemImage: "checkmark.circle")
                }
                .buttonStyle(.borderedProminent)

                if settings.hasStoredAPIKey {
                    Button(role: .destructive) {
                        settings.clearAPIKey()
                    } label: {
                        Label("清除 Key", systemImage: "trash")
                    }
                    .buttonStyle(.bordered)
                }
            }
            if !settings.saveMessage.isEmpty {
                Text(settings.saveMessage)
                    .font(AppTheme.Typography.footnote)
                    .foregroundStyle(AppTheme.ColorToken.mutedInk)
            }
        }
        .forestCard()
    }

    @ViewBuilder
    private func NativeAISettingsSection() -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            SectionTitle(systemImage: "sparkles", title: "iOS 原生智能")
            NativeAICapabilityRow(
                status: "已接入",
                title: "系统翻译",
                detail: "摘要、总结、全文块右上角可调用 iOS Translation 体验，适合快速对照阅读。"
            )
            NativeAICapabilityRow(
                status: "可规划",
                title: "Apple Intelligence 本机模型",
                detail: "适合离线摘要、关键词提取、检索问句改写；建议等目标系统提升到 iOS 26+ 后接入。"
            )
            NativeAICapabilityRow(
                status: "可规划",
                title: "App Intents",
                detail: "可做“打开今日论文森林”“缓存这篇 PDF”“生成阅读包”等 Siri 和 Spotlight 动作。"
            )
        }
        .forestCard()
    }

    @ViewBuilder
    private func CategorySettingsSection(categories: [CategoryRecord], newCategory: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            SectionTitle(systemImage: "tray.full", title: "arXiv 分类")
            ForEach(categories, id: \.code) { category in
                Toggle(category.code, isOn: Binding(get: {
                    category.enabled
                }, set: { value in
                    category.enabled = value
                    try? modelContext.save()
                }))
                .font(AppTheme.Typography.label)
            }
            HStack {
                TextField("新增分类，如 cs.RO", text: newCategory)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .paperInputStyle()
                Button {
                    let code = newCategory.wrappedValue.trimmingCharacters(in: .whitespacesAndNewlines)
                    guard !code.isEmpty else { return }
                    if !categories.contains(where: { $0.code == code }) {
                        modelContext.insert(CategoryRecord(code: code))
                        try? modelContext.save()
                    }
                    newCategory.wrappedValue = ""
                } label: {
                    Image(systemName: "plus")
                }
                .stableIconButtonStyle()
            }
        }
        .forestCard()
    }

    @ViewBuilder
    private func KeywordSettingsSection(groups: [KeywordGroupRecord], rules: [KeywordRuleRecord], newKeyword: Binding<String>) -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            SectionTitle(systemImage: "tag", title: "关键词规则")
            ForEach(groups, id: \.name) { group in
                VStack(alignment: .leading, spacing: AppTheme.Spacing.sm) {
                    Toggle(isOn: Binding(get: {
                        group.enabled
                    }, set: { value in
                        group.enabled = value
                        try? modelContext.save()
                    })) {
                        Text(group.name)
                            .font(AppTheme.Typography.cardTitle)
                    }
                    Stepper(value: Binding(get: {
                        group.weight
                    }, set: { value in
                        group.weight = value
                        try? modelContext.save()
                    }), in: 0.1...5.0, step: 0.1) {
                        Text("权重 \(group.weight, format: .number.precision(.fractionLength(1)))")
                            .font(AppTheme.Typography.label)
                            .foregroundStyle(AppTheme.ColorToken.mutedInk)
                    }
                    KeywordChips(keywords: rules.filter { $0.groupName == group.name && $0.kind == KeywordKind.include.rawValue && $0.enabled }.map(\.value))
                }
                .padding(AppTheme.Spacing.md)
                .background(AppTheme.ColorToken.paper.opacity(0.52), in: RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous))
            }
            if let firstGroup = groups.first {
                HStack {
                    TextField("给 \(firstGroup.name) 添加关键词", text: newKeyword)
                        .paperInputStyle()
                    Button {
                        let value = newKeyword.wrappedValue.trimmingCharacters(in: .whitespacesAndNewlines)
                        guard !value.isEmpty else { return }
                        modelContext.insert(KeywordRuleRecord(groupName: firstGroup.name, value: value, kind: .include))
                        try? modelContext.save()
                        newKeyword.wrappedValue = ""
                    } label: {
                        Image(systemName: "plus")
                    }
                    .stableIconButtonStyle()
                }
            }
        }
        .forestCard()
    }

    @ViewBuilder
    private func DataSettingsSection() -> some View {
        VStack(alignment: .leading, spacing: AppTheme.Spacing.md) {
            SectionTitle(systemImage: "externaldrive", title: "本地数据")
            Text("当前版本是本地单用户工作台；论文、收藏、AI 结果和 arXiv 页面缓存都保存在设备上。")
                .font(AppTheme.Typography.label)
                .foregroundStyle(AppTheme.ColorToken.mutedInk)
            HStack {
                Label("PDF 缓存", systemImage: "doc.richtext")
                    .font(AppTheme.Typography.label)
                    .foregroundStyle(AppTheme.ColorToken.ink)
                Spacer()
                Text(library.pdfCacheBytes.formattedBytes)
                    .font(AppTheme.Typography.metricSmall)
                    .foregroundStyle(AppTheme.ColorToken.mossDark)
            }
            .padding(AppTheme.Spacing.md)
            .background(AppTheme.ColorToken.paperDeep.opacity(0.72), in: RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous))
            Button {
                library.clearPDFCache()
            } label: {
                Label("清理 PDF 缓存", systemImage: "externaldrive.badge.xmark")
            }
            .buttonStyle(.bordered)
            Button(role: .destructive) {
                library.clearPapers(context: modelContext)
            } label: {
                Label("清理论文与缓存", systemImage: "trash")
            }
            .buttonStyle(.bordered)
        }
        .forestCard()
    }
}

struct NativeAICapabilityRow: View {
    let status: String
    let title: String
    let detail: String

    var body: some View {
        HStack(alignment: .top, spacing: AppTheme.Spacing.md) {
            Text(status)
                .font(AppTheme.Typography.captionStrong)
                .foregroundStyle(status == "已接入" ? Color.white : AppTheme.ColorToken.mossDark)
                .padding(.horizontal, AppTheme.Spacing.sm)
                .padding(.vertical, AppTheme.Spacing.xs)
                .background(status == "已接入" ? AppTheme.ColorToken.canopy : AppTheme.ColorToken.paperDeep, in: Capsule())
            VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                Text(title)
                    .font(AppTheme.Typography.cardTitle)
                    .foregroundStyle(AppTheme.ColorToken.ink)
                Text(detail)
                    .font(AppTheme.Typography.footnote)
                    .foregroundStyle(AppTheme.ColorToken.mutedInk)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(AppTheme.Spacing.md)
        .background(AppTheme.ColorToken.vellum.opacity(0.74), in: RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous))
    }
}

struct SettingsHero: View {
    var body: some View {
        HStack(spacing: AppTheme.Spacing.md) {
            BrandMark()
            VStack(alignment: .leading, spacing: AppTheme.Spacing.xs) {
                Text("独立 iOS 工作台")
                    .font(AppTheme.Typography.screenTitle)
                    .foregroundStyle(AppTheme.ColorToken.ink)
                Text("直接连接 arXiv 和你的模型 API，不依赖 Web 服务。")
                    .font(AppTheme.Typography.label)
                    .foregroundStyle(AppTheme.ColorToken.mutedInk)
            }
            Spacer()
        }
        .forestCard()
    }
}

struct SectionTitle: View {
    let systemImage: String
    let title: String

    var body: some View {
        Label(title, systemImage: systemImage)
            .font(AppTheme.Typography.cardTitle)
            .foregroundStyle(AppTheme.ColorToken.ink)
    }
}
