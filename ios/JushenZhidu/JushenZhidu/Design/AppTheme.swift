import SwiftUI
import UIKit

enum AppTheme {
    enum ColorToken {
        static let paper = Color.dynamic(light: UIColor(red: 0.99, green: 0.97, blue: 0.91, alpha: 1), dark: UIColor(red: 0.12, green: 0.16, blue: 0.12, alpha: 1))
        static let paperDeep = Color.dynamic(light: UIColor(red: 0.94, green: 0.88, blue: 0.76, alpha: 1), dark: UIColor(red: 0.20, green: 0.26, blue: 0.18, alpha: 1))
        static let vellum = Color.dynamic(light: UIColor(red: 0.98, green: 0.94, blue: 0.84, alpha: 1), dark: UIColor(red: 0.17, green: 0.20, blue: 0.15, alpha: 1))
        static let mist = Color.dynamic(light: UIColor(red: 0.89, green: 0.93, blue: 0.84, alpha: 1), dark: UIColor(red: 0.09, green: 0.14, blue: 0.11, alpha: 1))
        static let moss = Color(red: 0.45, green: 0.62, blue: 0.34)
        static let mossDark = Color.dynamic(light: UIColor(red: 0.10, green: 0.22, blue: 0.15, alpha: 1), dark: UIColor(red: 0.82, green: 0.91, blue: 0.72, alpha: 1))
        static let mossMuted = Color.dynamic(light: UIColor(red: 0.38, green: 0.48, blue: 0.35, alpha: 1), dark: UIColor(red: 0.66, green: 0.78, blue: 0.58, alpha: 1))
        static let canopy = Color(red: 0.17, green: 0.42, blue: 0.22)
        static let mapLight = Color.dynamic(light: UIColor(red: 0.71, green: 0.82, blue: 0.45, alpha: 1), dark: UIColor(red: 0.19, green: 0.29, blue: 0.16, alpha: 1))
        static let mapDeep = Color.dynamic(light: UIColor(red: 0.41, green: 0.61, blue: 0.32, alpha: 1), dark: UIColor(red: 0.11, green: 0.20, blue: 0.13, alpha: 1))
        static let fieldBackground = Color.dynamic(light: UIColor(red: 1.00, green: 0.98, blue: 0.92, alpha: 0.84), dark: UIColor(red: 0.15, green: 0.20, blue: 0.15, alpha: 0.92))
        static let warmAction = Color(red: 0.79, green: 0.37, blue: 0.25)
        static let copper = Color.dynamic(light: UIColor(red: 0.67, green: 0.31, blue: 0.21, alpha: 1), dark: UIColor(red: 0.94, green: 0.57, blue: 0.38, alpha: 1))
        static let arxivBlue = Color(red: 0.03, green: 0.45, blue: 0.66)
        static let line = Color.dynamic(light: UIColor(red: 0.79, green: 0.74, blue: 0.65, alpha: 1), dark: UIColor(red: 0.33, green: 0.42, blue: 0.31, alpha: 1))
        static let lineSoft = Color.dynamic(light: UIColor(red: 0.89, green: 0.85, blue: 0.77, alpha: 1), dark: UIColor(red: 0.26, green: 0.34, blue: 0.25, alpha: 1))
        static let success = Color(red: 0.11, green: 0.52, blue: 0.29)
        static let warning = Color(red: 0.90, green: 0.58, blue: 0.16)
        static let danger = Color(red: 0.70, green: 0.14, blue: 0.10)
        static let ink = Color.dynamic(light: UIColor(red: 0.09, green: 0.18, blue: 0.13, alpha: 1), dark: UIColor(red: 0.91, green: 0.94, blue: 0.86, alpha: 1))
        static let mutedInk = Color.dynamic(light: UIColor(red: 0.35, green: 0.43, blue: 0.37, alpha: 1), dark: UIColor(red: 0.70, green: 0.76, blue: 0.66, alpha: 1))
    }

    enum Spacing {
        static let xs: CGFloat = 4
        static let sm: CGFloat = 8
        static let md: CGFloat = 12
        static let lg: CGFloat = 16
        static let xl: CGFloat = 24
        static let xxl: CGFloat = 32
    }

    enum Radius {
        static let card: CGFloat = 8
        static let control: CGFloat = 8
        static let sheet: CGFloat = 18
    }

    enum Motion {
        static let panel: Animation = .spring(response: 0.30, dampingFraction: 0.86, blendDuration: 0.08)
        static let drawer: Animation = .interactiveSpring(response: 0.38, dampingFraction: 0.88, blendDuration: 0.12)
        static let control: Animation = .spring(response: 0.22, dampingFraction: 0.84, blendDuration: 0.06)
        static let status: Animation = .easeInOut(duration: 0.26)
        static let press: Animation = .spring(response: 0.18, dampingFraction: 0.72, blendDuration: 0.04)
    }

    enum Typography {
        private static let displayFontNames = ["STSongti-SC-Bold", "STSongti-TC-Bold", "Songti SC Bold", "Songti TC Bold"]
        private static let bodyRegularFontNames = ["PingFangSC-Regular", "PingFangTC-Regular", "HiraSansGB-W3"]
        private static let bodyMediumFontNames = ["PingFangSC-Medium", "PingFangTC-Medium", "HiraSansGB-W6"]
        private static let bodySemiboldFontNames = ["PingFangSC-Semibold", "PingFangTC-Semibold", "HiraSansGB-W6"]

        static let display = preferred(
            displayFontNames,
            size: 34,
            relativeTo: .largeTitle,
            fallback: .system(.largeTitle, design: .serif, weight: .heavy)
        )
        static let screenTitle = preferred(
            displayFontNames,
            size: 24,
            relativeTo: .title2,
            fallback: .system(.title2, design: .serif, weight: .bold)
        )
        static let sectionTitle = preferred(
            displayFontNames,
            size: 22,
            relativeTo: .title3,
            fallback: .system(.title3, design: .serif, weight: .bold)
        )
        static let chineseTitle = preferred(
            displayFontNames,
            size: 21,
            relativeTo: .headline,
            fallback: .system(.headline, design: .serif, weight: .bold)
        )
        static let chineseAction = preferred(
            displayFontNames,
            size: 17,
            relativeTo: .callout,
            fallback: .system(.callout, design: .serif, weight: .bold)
        )
        static let chineseLabel = preferred(
            displayFontNames,
            size: 15,
            relativeTo: .subheadline,
            fallback: .system(.subheadline, design: .serif, weight: .semibold)
        )
        static let chineseCaption = preferred(
            displayFontNames,
            size: 12,
            relativeTo: .caption,
            fallback: .system(.caption, design: .serif, weight: .semibold)
        )
        static let englishCardTitle = preferred(
            displayFontNames,
            size: 20,
            relativeTo: .headline,
            fallback: .system(.headline, design: .serif, weight: .bold)
        )
        static let englishHeading = preferred(
            displayFontNames,
            size: 19,
            relativeTo: .headline,
            fallback: .system(.headline, design: .serif, weight: .bold)
        )
        static let englishBody = preferred(
            displayFontNames,
            size: 18,
            relativeTo: .body,
            fallback: .system(.body, design: .serif)
        )
        static let englishLabel = preferred(
            displayFontNames,
            size: 16,
            relativeTo: .subheadline,
            fallback: .system(.subheadline, design: .serif, weight: .semibold)
        )
        static let englishFootnote = preferred(
            displayFontNames,
            size: 14,
            relativeTo: .footnote,
            fallback: .system(.footnote, design: .serif)
        )
        static let englishCaption = preferred(
            displayFontNames,
            size: 12,
            relativeTo: .caption,
            fallback: .system(.caption, design: .serif, weight: .semibold)
        )
        static let cardTitle = preferred(
            bodySemiboldFontNames,
            size: 17,
            relativeTo: .headline,
            fallback: .system(.headline, design: .default, weight: .semibold)
        )
        static let body = preferred(
            bodyRegularFontNames,
            size: 17,
            relativeTo: .body,
            fallback: .system(.body, design: .default)
        )
        static let bodyEmphasis = preferred(
            bodyMediumFontNames,
            size: 15,
            relativeTo: .subheadline,
            fallback: .system(.subheadline, design: .default, weight: .semibold)
        )
        static let label = preferred(
            bodyMediumFontNames,
            size: 15,
            relativeTo: .subheadline,
            fallback: .system(.subheadline, design: .default, weight: .semibold)
        )
        static let action = preferred(
            bodySemiboldFontNames,
            size: 16,
            relativeTo: .callout,
            fallback: .system(.callout, design: .default, weight: .bold)
        )
        static let footnote = preferred(
            bodyRegularFontNames,
            size: 13,
            relativeTo: .footnote,
            fallback: .system(.footnote, design: .default)
        )
        static let footnoteEmphasis = preferred(
            bodyMediumFontNames,
            size: 13,
            relativeTo: .footnote,
            fallback: .system(.footnote, design: .default, weight: .semibold)
        )
        static let caption = preferred(
            bodyMediumFontNames,
            size: 12,
            relativeTo: .caption,
            fallback: .system(.caption, design: .default, weight: .semibold)
        )
        static let captionStrong = preferred(
            bodySemiboldFontNames,
            size: 12,
            relativeTo: .caption,
            fallback: .system(.caption, design: .default, weight: .bold)
        )
        static let captionSmall = preferred(
            bodyMediumFontNames,
            size: 11,
            relativeTo: .caption2,
            fallback: .system(.caption2, design: .default, weight: .semibold)
        )
        static let captionSmallStrong = preferred(
            bodySemiboldFontNames,
            size: 11,
            relativeTo: .caption2,
            fallback: .system(.caption2, design: .default, weight: .bold)
        )
        static let metric = preferred(
            ["AvenirNextCondensed-Heavy", "AvenirNext-Heavy"],
            size: 30,
            relativeTo: .title,
            fallback: .system(.title, design: .default, weight: .heavy)
        )
        static let number = Font.system(.callout, design: .monospaced, weight: .bold)
        static let metricSmall = Font.system(.caption, design: .monospaced, weight: .bold)
        static let metricTiny = Font.system(.caption2, design: .monospaced, weight: .heavy)
        static let metricHeadline = Font.system(.headline, design: .monospaced, weight: .bold)
        static let monoCaption = metricSmall

        static func uiDisplayFont(size: CGFloat) -> UIFont {
            uiFont(displayFontNames, size: size, fallbackWeight: .bold)
        }

        static func uiSemiboldFont(size: CGFloat) -> UIFont {
            uiFont(bodySemiboldFontNames, size: size, fallbackWeight: .semibold)
        }

        static func uiMediumFont(size: CGFloat) -> UIFont {
            uiFont(bodyMediumFontNames, size: size, fallbackWeight: .medium)
        }

        private static func preferred(_ names: [String], size: CGFloat, relativeTo style: Font.TextStyle, fallback: Font) -> Font {
            for name in names where UIFont(name: name, size: size) != nil {
                return .custom(name, size: size, relativeTo: style)
            }
            return fallback
        }

        private static func uiFont(_ names: [String], size: CGFloat, fallbackWeight: UIFont.Weight) -> UIFont {
            for name in names {
                if let font = UIFont(name: name, size: size) {
                    return font
                }
            }
            return .systemFont(ofSize: size, weight: fallbackWeight)
        }
    }

    static let cardShadow = Color.black.opacity(0.10)
    static let softShadow = Color.black.opacity(0.06)

    static func configureAppAppearance() {
        UINavigationBar.appearance().titleTextAttributes = [
            .font: Typography.uiDisplayFont(size: 18),
            .foregroundColor: UIColor.label
        ]
        UINavigationBar.appearance().largeTitleTextAttributes = [
            .font: Typography.uiDisplayFont(size: 34),
            .foregroundColor: UIColor.label
        ]

        let tabFont = Typography.uiMediumFont(size: 11)
        UITabBarItem.appearance().setTitleTextAttributes([.font: tabFont], for: .normal)
        UITabBarItem.appearance().setTitleTextAttributes([.font: tabFont], for: .selected)

        let segmentedFont = Typography.uiMediumFont(size: 13)
        UISegmentedControl.appearance().setTitleTextAttributes([.font: segmentedFont], for: .normal)
        UISegmentedControl.appearance().setTitleTextAttributes([.font: segmentedFont], for: .selected)
    }
}

extension View {
    func forestCard(padding: CGFloat = AppTheme.Spacing.lg) -> some View {
        self
            .padding(padding)
            .background(AppTheme.ColorToken.paper.opacity(0.96), in: RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: AppTheme.Radius.card, style: .continuous)
                    .stroke(AppTheme.ColorToken.lineSoft, lineWidth: 1)
            }
            .shadow(color: AppTheme.softShadow, radius: 12, x: 0, y: 8)
    }

    func stableIconButtonStyle() -> some View {
        self
            .frame(width: 40, height: 40)
            .background(AppTheme.ColorToken.paper, in: RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous)
                    .stroke(AppTheme.ColorToken.lineSoft, lineWidth: 1)
            }
    }

    func paperInputStyle() -> some View {
        self
            .font(AppTheme.Typography.body)
            .padding(.horizontal, AppTheme.Spacing.md)
            .padding(.vertical, AppTheme.Spacing.sm)
            .foregroundStyle(AppTheme.ColorToken.ink)
            .background(AppTheme.ColorToken.fieldBackground, in: RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: AppTheme.Radius.control, style: .continuous)
                    .stroke(AppTheme.ColorToken.lineSoft, lineWidth: 1)
            }
    }
}

struct ForestPressButtonStyle: ButtonStyle {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var scale: CGFloat = 0.97

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed && !reduceMotion ? scale : 1)
            .opacity(configuration.isPressed ? 0.88 : 1)
            .animation(reduceMotion ? nil : AppTheme.Motion.press, value: configuration.isPressed)
    }
}

extension ButtonStyle where Self == ForestPressButtonStyle {
    static var forestPress: ForestPressButtonStyle {
        ForestPressButtonStyle()
    }
}

private extension Color {
    static func dynamic(light: UIColor, dark: UIColor) -> Color {
        Color(uiColor: UIColor { traits in
            traits.userInterfaceStyle == .dark ? dark : light
        })
    }
}

extension Int64 {
    var formattedBytes: String {
        ByteCountFormatter.string(fromByteCount: self, countStyle: .file)
    }
}

struct BrandMark: View {
    var size: CGFloat = 52

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: size * 0.25, style: .continuous)
                .fill(
                    LinearGradient(
                        colors: [AppTheme.ColorToken.canopy, Color(red: 0.08, green: 0.18, blue: 0.12)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .overlay {
                    RoundedRectangle(cornerRadius: size * 0.25, style: .continuous)
                        .stroke(AppTheme.ColorToken.lineSoft.opacity(0.55), lineWidth: 1)
                }

            RoundedRectangle(cornerRadius: size * 0.12, style: .continuous)
                .fill(AppTheme.ColorToken.paperDeep)
                .frame(width: size * 0.48, height: size * 0.62)
                .rotationEffect(.degrees(-8))
                .offset(x: -size * 0.08, y: size * 0.04)
                .shadow(color: Color.black.opacity(0.18), radius: size * 0.08, x: 0, y: size * 0.05)

            RoundedRectangle(cornerRadius: size * 0.12, style: .continuous)
                .fill(AppTheme.ColorToken.vellum)
                .frame(width: size * 0.48, height: size * 0.62)
                .rotationEffect(.degrees(6))
                .offset(x: size * 0.09, y: 0)

            Capsule()
                .fill(AppTheme.ColorToken.mossDark.opacity(0.38))
                .frame(width: size * 0.05, height: size * 0.42)
                .rotationEffect(.degrees(4))
                .offset(x: size * 0.03, y: size * 0.03)

            Capsule()
                .fill(AppTheme.ColorToken.copper)
                .frame(width: size * 0.10, height: size * 0.28)
                .offset(x: size * 0.17, y: -size * 0.12)

            Capsule()
                .fill(AppTheme.ColorToken.mossDark)
                .frame(width: size * 0.07, height: size * 0.24)
                .offset(x: -size * 0.02, y: size * 0.12)

            Circle()
                .fill(AppTheme.ColorToken.moss)
                .frame(width: size * 0.26, height: size * 0.26)
                .offset(x: -size * 0.10, y: -size * 0.03)
            Circle()
                .fill(AppTheme.ColorToken.mapLight)
                .frame(width: size * 0.22, height: size * 0.22)
                .offset(x: size * 0.02, y: -size * 0.09)
            Circle()
                .fill(AppTheme.ColorToken.mossDark)
                .frame(width: size * 0.20, height: size * 0.20)
                .offset(x: size * 0.10, y: -size * 0.01)

            Path { path in
                path.move(to: CGPoint(x: size * 0.30, y: size * 0.75))
                path.addQuadCurve(
                    to: CGPoint(x: size * 0.73, y: size * 0.72),
                    control: CGPoint(x: size * 0.50, y: size * 0.86)
                )
            }
            .stroke(AppTheme.ColorToken.warmAction, style: StrokeStyle(lineWidth: size * 0.055, lineCap: .round))

            Path { path in
                path.move(to: CGPoint(x: size * 0.64, y: size * 0.25))
                path.addLine(to: CGPoint(x: size * 0.76, y: size * 0.18))
            }
            .stroke(AppTheme.ColorToken.arxivBlue.opacity(0.78), style: StrokeStyle(lineWidth: size * 0.025, lineCap: .round))

            Circle()
                .fill(AppTheme.ColorToken.arxivBlue)
                .frame(width: size * 0.08, height: size * 0.08)
                .offset(x: size * 0.19, y: -size * 0.17)

            Circle()
                .fill(AppTheme.ColorToken.arxivBlue.opacity(0.76))
                .frame(width: size * 0.055, height: size * 0.055)
                .offset(x: size * 0.31, y: -size * 0.24)
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}
