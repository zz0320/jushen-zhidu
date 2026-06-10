import SwiftData
import SwiftUI

struct MainTabView: View {
    @Environment(\.modelContext) private var modelContext
    @EnvironmentObject private var library: LibraryViewModel

    var body: some View {
        TabView {
            ForestView()
                .tabItem {
                    Label("森林", systemImage: "tree")
                }
                .accessibilityIdentifier("tab.forest")

            PapersListView(favoritesOnly: false)
                .tabItem {
                    Label("论文", systemImage: "doc.text.magnifyingglass")
                }
                .accessibilityIdentifier("tab.papers")

            PapersListView(favoritesOnly: true)
                .tabItem {
                    Label("收藏", systemImage: "bookmark.fill")
                }
                .accessibilityIdentifier("tab.favorites")

            SettingsView()
                .tabItem {
                    Label("设置", systemImage: "slider.horizontal.3")
                }
                .accessibilityIdentifier("tab.settings")
        }
        .font(AppTheme.Typography.body)
        .onAppear {
            library.seedDefaultsIfNeeded(context: modelContext)
        }
        .safeAreaInset(edge: .top, spacing: 0) {
            if let activity = library.activeTask {
                TaskProgressFloatingCard(activity: activity) {
                    withAnimation(.spring(response: 0.28, dampingFraction: 0.88)) {
                        library.activeTask = nil
                    }
                }
                .padding(.horizontal, AppTheme.Spacing.lg)
                .padding(.top, AppTheme.Spacing.sm)
                .padding(.bottom, AppTheme.Spacing.xs)
                .transition(.move(edge: .top).combined(with: .opacity))
            }
        }
        .animation(.spring(response: 0.28, dampingFraction: 0.88), value: library.activeTask)
    }
}

struct TaskProgressFloatingCard: View {
    let activity: TaskActivity
    let dismiss: () -> Void

    var body: some View {
        HStack(spacing: AppTheme.Spacing.md) {
            ZStack {
                Circle()
                    .stroke(AppTheme.ColorToken.lineSoft, lineWidth: 4)
                Circle()
                    .trim(from: 0, to: max(0.02, min(activity.percent, 1)))
                    .stroke(progressColor, style: StrokeStyle(lineWidth: 4, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                Image(systemName: iconName)
                    .font(AppTheme.Typography.captionStrong)
                    .foregroundStyle(progressColor)
            }
            .frame(width: 34, height: 34)

            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: AppTheme.Spacing.xs) {
                    Text(activity.title)
                        .font(AppTheme.Typography.chineseLabel)
                        .foregroundStyle(AppTheme.ColorToken.ink)
                    Text("\(Int(activity.percent * 100))%")
                        .font(AppTheme.Typography.metricSmall)
                        .foregroundStyle(progressColor)
                }
                Text(activity.message)
                    .font(AppTheme.Typography.footnote)
                    .foregroundStyle(AppTheme.ColorToken.mutedInk)
                    .lineLimit(1)
            }

            Spacer(minLength: 0)

            if activity.isTerminal {
                Button(action: dismiss) {
                    Image(systemName: "xmark")
                        .font(AppTheme.Typography.captionStrong)
                        .frame(width: 30, height: 30)
                        .background(AppTheme.ColorToken.vellum.opacity(0.78), in: Circle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("关闭任务进度")
            }
        }
        .padding(.horizontal, AppTheme.Spacing.md)
        .padding(.vertical, AppTheme.Spacing.sm)
        .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: AppTheme.Radius.sheet, style: .continuous))
        .background(AppTheme.ColorToken.paper.opacity(0.90), in: RoundedRectangle(cornerRadius: AppTheme.Radius.sheet, style: .continuous))
        .overlay(alignment: .bottom) {
            ProgressView(value: activity.percent)
                .tint(progressColor)
                .scaleEffect(x: 1, y: 0.7)
                .padding(.horizontal, AppTheme.Spacing.md)
                .offset(y: -2)
        }
        .overlay {
            RoundedRectangle(cornerRadius: AppTheme.Radius.sheet, style: .continuous)
                .stroke(AppTheme.ColorToken.lineSoft, lineWidth: 1)
        }
        .shadow(color: Color.black.opacity(0.14), radius: 14, x: 0, y: 8)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(activity.title)：\(activity.message)，进度 \(Int(activity.percent * 100))%")
    }

    private var progressColor: Color {
        if activity.stage == "failed" {
            return AppTheme.ColorToken.danger
        }
        if activity.stage == "complete" {
            return AppTheme.ColorToken.success
        }
        return AppTheme.ColorToken.warmAction
    }

    private var iconName: String {
        if activity.stage == "failed" {
            return "exclamationmark"
        }
        if activity.stage == "complete" {
            return "checkmark"
        }
        return "leaf"
    }
}
