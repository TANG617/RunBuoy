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
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency
    @Environment(\.colorSchemeContrast) private var contrast

    var body: some View {
        HStack(spacing: 6) {
            Image(systemName: presentation.symbol)
                .accessibilityHidden(true)
            Text(presentation.title)
        }
        .font(.caption.weight(.semibold))
        .foregroundStyle(presentation.color)
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
    let progress: RunProgress?
    let phase: String?
    let showsIndeterminate: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let progress {
                if let fraction = progress.boundedFraction {
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
                } else if showsIndeterminate {
                    HStack(spacing: 8) {
                        Image(systemName: "ellipsis")
                            .accessibilityHidden(true)
                        Text("progress.indeterminate")
                    }
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                }
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
            Label(run.machineName, systemImage: "desktopcomputer")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .lineLimit(1)
            RunProgressView(
                progress: run.progress,
                phase: run.phase,
                showsIndeterminate: run.executionStatus.isActive
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
        .foregroundStyle(.secondary)
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
    }
}
