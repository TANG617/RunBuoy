import SwiftUI

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
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        Label {
            Text(presentation.title)
        } icon: {
            Image(systemName: presentation.symbol)
        }
        .font(.caption.weight(.semibold))
        .foregroundStyle(presentation.color)
        .padding(.horizontal, 9)
        .padding(.vertical, 5)
        .background(presentation.color.opacity(contrast == .increased ? 0.2 : 0.12), in: Capsule())
        .overlay {
            if contrast == .increased {
                Capsule().stroke(presentation.color, lineWidth: 1)
            }
        }
    }
}

struct RunProgressView: View {
    let progress: RunProgress?
    let phase: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let progress, let fraction = progress.boundedFraction {
                ProgressView(value: fraction)
                    .accessibilityLabel("run.progress")
                    .accessibilityValue(Text(fraction, format: .percent))
                HStack {
                    if let current = progress.current, let total = progress.total {
                        Text("\(current, format: .number) / \(total, format: .number)")
                    }
                    Spacer()
                    Text(fraction, format: .percent.precision(.fractionLength(0)))
                        .fontWeight(.semibold)
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            } else {
                HStack(spacing: 8) {
                    Image(systemName: "ellipsis")
                        .accessibilityHidden(true)
                    Text("progress.indeterminate")
                }
                .font(.subheadline)
                .foregroundStyle(.secondary)
            }
            if let phase, !phase.isEmpty {
                Text(phase)
                    .font(.subheadline.weight(.medium))
                    .lineLimit(2)
                    .accessibilityLabel(String(localized: "run.phase"))
                    .accessibilityValue(phase)
            }
        }
    }
}

struct RunRow: View {
    let run: RunSnapshot

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline) {
                Text(run.title)
                    .font(.headline)
                    .lineLimit(2)
                Spacer(minLength: 8)
                StatusBadge(presentation: run.executionStatus.presentation)
            }
            Label(run.machineName, systemImage: "desktopcomputer")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .lineLimit(1)
            RunProgressView(progress: run.progress, phase: run.phase)
            HStack {
                if run.healthStatus != .healthy {
                    Label(run.healthStatus.presentation.title, systemImage: run.healthStatus.presentation.symbol)
                }
                if run.attentionStatus != .none {
                    Label(run.attentionStatus.presentation.title, systemImage: run.attentionStatus.presentation.symbol)
                }
                Spacer()
                Text(run.updatedAt, format: .relative(presentation: .named))
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .padding(.vertical, 6)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}

struct OfflineBanner: View {
    let message: String

    var body: some View {
        Label {
            VStack(alignment: .leading, spacing: 2) {
                Text("runs.cached_data")
                    .fontWeight(.semibold)
                Text(message)
                    .font(.caption)
                    .lineLimit(2)
            }
        } icon: {
            Image(systemName: "wifi.slash")
        }
        .foregroundStyle(.orange)
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.orange.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
        .accessibilityElement(children: .combine)
    }
}
