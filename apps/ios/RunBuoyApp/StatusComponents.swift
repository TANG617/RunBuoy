import SwiftUI

struct MachineIconImage: View {
    @AppStorage private var iconName: String

    init(machineID: String) {
        _iconName = AppStorage(
            wrappedValue: MachineIcon.defaultValue.rawValue,
            MachineIcon.key(for: machineID)
        )
    }

    var body: some View {
        Image(systemName: resolvedIcon.rawValue)
    }

    private var resolvedIcon: MachineIcon {
        MachineIcon(rawValue: iconName) ?? .defaultValue
    }
}

struct RefreshButton: View {
    let isRefreshing: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Label {
                Text("common.refresh")
            } icon: {
                Image(systemName: "arrow.clockwise")
                    .symbolEffect(
                        .rotate,
                        options: .repeat(.continuous),
                        isActive: isRefreshing
                    )
            }
        }
        .disabled(isRefreshing)
    }
}

struct StatusPresentation {
    let title: LocalizedStringKey
    let symbol: String
    let color: Color
}

extension ExecutionStatus {
    var presentation: StatusPresentation {
        switch self {
        case .created:
            StatusPresentation(title: "status.created", symbol: "circle.dotted", color: .secondary)
        case .starting:
            StatusPresentation(title: "status.starting", symbol: "hourglass", color: .blue)
        case .running:
            StatusPresentation(title: "status.running", symbol: "waveform.path.ecg", color: .blue)
        case .succeeded:
            StatusPresentation(title: "status.succeeded", symbol: "checkmark.circle.fill", color: .green)
        case .failed:
            StatusPresentation(title: "status.failed", symbol: "xmark.octagon.fill", color: .red)
        case .cancelled:
            StatusPresentation(title: "status.cancelled", symbol: "minus.circle.fill", color: .orange)
        case .lost:
            StatusPresentation(title: "status.lost", symbol: "questionmark.diamond.fill", color: .orange)
        case .unknown:
            StatusPresentation(title: "status.unknown", symbol: "questionmark.circle", color: .secondary)
        }
    }

    var progressTint: Color {
        switch self {
        case .succeeded:
            .green
        case .failed:
            .red
        case .cancelled, .lost:
            .orange
        case .created, .starting, .running, .unknown:
            .accentColor
        }
    }
}

extension HealthStatus {
    var presentation: StatusPresentation {
        switch self {
        case .healthy:
            StatusPresentation(title: "health.healthy", symbol: "checkmark.shield", color: .green)
        case .stale:
            StatusPresentation(title: "health.stale", symbol: "clock.badge.exclamationmark", color: .orange)
        case .offline:
            StatusPresentation(title: "health.offline", symbol: "wifi.slash", color: .secondary)
        case .unknown:
            StatusPresentation(title: "status.unknown", symbol: "questionmark.circle", color: .secondary)
        }
    }
}

extension AttentionStatus {
    var presentation: StatusPresentation {
        switch self {
        case .none:
            StatusPresentation(title: "attention.none", symbol: "checkmark", color: .secondary)
        case .information:
            StatusPresentation(title: "attention.information", symbol: "info.circle.fill", color: .blue)
        case .warning:
            StatusPresentation(title: "attention.warning", symbol: "exclamationmark.triangle.fill", color: .orange)
        case .actionRequired:
            StatusPresentation(title: "attention.action_required", symbol: "exclamationmark.bubble.fill", color: .red)
        case .unknown:
            StatusPresentation(title: "status.unknown", symbol: "questionmark.circle", color: .secondary)
        }
    }
}

struct StatusBadge: View {
    let presentation: StatusPresentation
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: presentation.symbol)
                .accessibilityHidden(true)
                .foregroundStyle(presentation.color)
            Text(presentation.title)
                .foregroundStyle(.primary)
        }
        .font(.caption.weight(.semibold))
        .padding(.horizontal, 9)
        .padding(.vertical, 5)
        .background(
            reduceTransparency
                ? Color(uiColor: .secondarySystemBackground)
                : presentation.color.opacity(contrast == .increased ? 0.2 : 0.12),
            in: Capsule()
        )
        .overlay {
            if contrast == .increased || reduceTransparency {
                Capsule().stroke(presentation.color, lineWidth: 1)
            }
        }
        .lineLimit(1)
        .fixedSize(horizontal: true, vertical: false)
    }
}

struct RunProgressView: View {
    enum Emphasis: Equatable {
        case compact
        case prominent

        var barHeight: CGFloat {
            switch self {
            case .compact: 9
            case .prominent: 14
            }
        }

        var spacing: CGFloat {
            switch self {
            case .compact: 7
            case .prominent: 10
            }
        }

        var phaseFont: Font {
            switch self {
            case .compact: .subheadline.weight(.medium)
            case .prominent: .headline
            }
        }

        var percentageFont: Font {
            switch self {
            case .compact: .subheadline.weight(.bold)
            case .prominent: .title.bold()
            }
        }
    }

    let progress: RunProgress?
    let phase: String?
    let showsIndeterminate: Bool
    var emphasis: Emphasis = .compact
    var tint: Color = .accentColor
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        VStack(alignment: .leading, spacing: emphasis.spacing) {
            if let fraction = progress?.boundedFraction {
                determinateContent(fraction: fraction)
            } else if showsIndeterminate {
                indeterminateContent
            } else if let phase, !phase.isEmpty {
                phaseLabel(phase)
            }
        }
    }

    private func determinateContent(fraction: Double) -> some View {
        VStack(alignment: .leading, spacing: emphasis.spacing) {
            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 4) {
                    progressLabel
                    percentageLabel(fraction)
                }
            } else {
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    progressLabel
                    Spacer(minLength: 8)
                    percentageLabel(fraction)
                }
            }

            DeterminateRunProgressBar(
                fraction: fraction,
                tint: tint,
                height: emphasis.barHeight,
                addsGlow: emphasis == .prominent
            )

            if let progress,
               let current = progress.current,
               let total = progress.total {
                let count = "\(current.formatted()) / \(total.formatted())"
                let value = progress.unit.flatMap { unit in
                    unit.isEmpty ? nil : "\(count) \(unit)"
                } ?? count
                Text(value)
                .font(.caption)
                .foregroundStyle(.primary)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibleProgressLabel)
        .accessibilityValue(Text(fraction, format: .percent))
    }

    private var indeterminateContent: some View {
        VStack(alignment: .leading, spacing: emphasis.spacing) {
            progressLabel
            IndeterminateRunProgressBar(
                tint: tint,
                height: emphasis.barHeight
            )
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibleProgressLabel)
        .accessibilityValue("progress.indeterminate")
    }

    @ViewBuilder
    private var progressLabel: some View {
        if let phase, !phase.isEmpty {
            phaseLabel(phase)
        } else {
            Text("run.progress")
                .font(emphasis.phaseFont)
        }
    }

    private func phaseLabel(_ phase: String) -> some View {
        Text(phase)
            .font(emphasis.phaseFont)
            .lineLimit(emphasis == .prominent ? 3 : 2)
            .accessibilityLabel(String(localized: "run.phase"))
            .accessibilityValue(phase)
    }

    private func percentageLabel(_ fraction: Double) -> some View {
        Text(
            fraction.formatted(
                .percent.precision(.fractionLength(0))
            )
        )
            .font(emphasis.percentageFont)
            .foregroundStyle(.primary)
            .accessibilityHidden(true)
    }

    private var accessibleProgressLabel: String {
        let label = String(localized: "run.progress")
        guard let phase, !phase.isEmpty else { return label }
        return "\(label): \(phase)"
    }
}

private struct DeterminateRunProgressBar: View {
    let fraction: Double
    let tint: Color
    let height: CGFloat
    let addsGlow: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        GeometryReader { proxy in
            ZStack(alignment: .leading) {
                Capsule()
                    .fill(tint.opacity(contrast == .increased ? 0.28 : 0.15))
                Capsule()
                    .fill(
                        LinearGradient(
                            colors: [tint.opacity(0.78), tint],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
                    .frame(width: proxy.size.width * fraction)
                    .shadow(
                        color: addsGlow ? tint.opacity(0.34) : .clear,
                        radius: addsGlow ? 6 : 0,
                        y: 1
                    )
            }
        }
        .frame(height: height)
        .animation(reduceMotion ? nil : .smooth(duration: 0.4), value: fraction)
        .accessibilityHidden(true)
    }
}

private struct IndeterminateRunProgressBar: View {
    let tint: Color
    let height: CGFloat
    @State private var isAnimating = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        GeometryReader { proxy in
            let segmentWidth = proxy.size.width * 0.36
            ZStack(alignment: .leading) {
                Capsule()
                    .fill(tint.opacity(contrast == .increased ? 0.28 : 0.15))
                Capsule()
                    .fill(
                        LinearGradient(
                            colors: [tint.opacity(0.62), tint],
                            startPoint: .leading,
                            endPoint: .trailing
                        )
                    )
                    .frame(width: segmentWidth)
                    .offset(
                        x: reduceMotion
                            ? (proxy.size.width - segmentWidth) / 2
                            : (isAnimating ? proxy.size.width : -segmentWidth)
                    )
            }
            .clipShape(Capsule())
        }
        .frame(height: height)
        .animation(
            reduceMotion
                ? nil
                : .linear(duration: 1.15).repeatForever(autoreverses: false),
            value: isAnimating
        )
        .onAppear {
            isAnimating = !reduceMotion
        }
        .onChange(of: reduceMotion) { _, shouldReduceMotion in
            isAnimating = !shouldReduceMotion
        }
    }
}

struct RunRow: View {
    let model: RunSummaryModel

    var body: some View {
        RunRowContent(run: model.snapshot)
    }
}

private struct RunRowContent: View {
    let run: RunSnapshot
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 8) {
                    runTitle
                    StatusBadge(presentation: run.executionStatus.presentation)
                }
            } else {
                HStack(alignment: .firstTextBaseline) {
                    runTitle
                    Spacer(minLength: 8)
                    StatusBadge(presentation: run.executionStatus.presentation)
                }
            }
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                MachineIconImage(machineID: run.machineID)
                    .accessibilityHidden(true)
                Text(run.machineName)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .font(.subheadline)
            .foregroundStyle(.primary)
            RunProgressView(
                progress: run.progress,
                phase: run.phase,
                showsIndeterminate: run.executionStatus.isActive,
                tint: run.executionStatus.progressTint
            )
            RunRowMetadataFooter(run: run)
        }
        .padding(.vertical, 6)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }

    private var runTitle: some View {
        Text(run.title)
            .font(.headline)
            .lineLimit(dynamicTypeSize.isAccessibilitySize ? 3 : 2)
    }
}

private struct RunRowMetadataFooter: View {
    let run: RunSnapshot

    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack {
                statusLabels
                Spacer()
                updateTime
            }

            VStack(alignment: .leading, spacing: 6) {
                statusLabels
                updateTime
            }
        }
        .font(.caption)
        .foregroundStyle(.primary)
    }

    @ViewBuilder
    private var statusLabels: some View {
        HStack(spacing: 8) {
            if run.healthStatus != .healthy {
                HStack(spacing: 4) {
                    Image(systemName: run.healthStatus.presentation.symbol)
                        .accessibilityHidden(true)
                    Text(run.healthStatus.presentation.title)
                }
                    .fixedSize(horizontal: true, vertical: false)
            }
            if run.attentionStatus != .none {
                HStack(spacing: 4) {
                    Image(systemName: run.attentionStatus.presentation.symbol)
                        .accessibilityHidden(true)
                    Text(run.attentionStatus.presentation.title)
                }
                    .fixedSize(horizontal: true, vertical: false)
            }
        }
    }

    private var updateTime: some View {
        Text(run.updatedAt, format: .relative(presentation: .named))
            .fixedSize(horizontal: true, vertical: false)
    }
}

struct OfflineBanner: View {
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    let message: String

    var body: some View {
        Group {
            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 8) {
                    offlineIcon
                    bannerText
                }
            } else {
                HStack(alignment: .top, spacing: 8) {
                    offlineIcon
                    bannerText
                }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            reduceTransparency ? Color(uiColor: .secondarySystemBackground) : .orange.opacity(0.12),
            in: RoundedRectangle(cornerRadius: 12)
        )
        .overlay {
            if reduceTransparency || contrast == .increased {
                RoundedRectangle(cornerRadius: 12)
                    .stroke(.orange, lineWidth: 1)
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("runs.offlineBanner")
    }

    private var offlineIcon: some View {
        Image(systemName: "wifi.slash")
            .foregroundStyle(.orange)
            .accessibilityHidden(true)
    }

    private var bannerText: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("runs.cached_data")
                .fontWeight(.semibold)
                .lineLimit(nil)
                .fixedSize(horizontal: false, vertical: true)
            Text(message)
                .font(.caption)
                .lineLimit(nil)
                .fixedSize(horizontal: false, vertical: true)
        }
        .foregroundStyle(.primary)
        .layoutPriority(1)
    }
}
