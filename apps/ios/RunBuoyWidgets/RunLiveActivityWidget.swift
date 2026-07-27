import ActivityKit
import SwiftUI
import UIKit
import WidgetKit

struct RunLiveActivityWidget: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: RunActivityAttributes.self) { context in
            RunLockScreenView(attributes: context.attributes, state: context.state)
                .activityBackgroundTint(Color(uiColor: .secondarySystemBackground))
                .activitySystemActionForegroundColor(.primary)
                .widgetURL(deepLink(runID: context.attributes.runID))
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    LiveStatusIcon(state: context.state, size: 24)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    LiveProgressText(state: context.state)
                        .font(.headline.monospacedDigit())
                }
                DynamicIslandExpandedRegion(.center) {
                    Text(context.attributes.title)
                        .font(.headline)
                        .lineLimit(1)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    VStack(alignment: .leading, spacing: 6) {
                        HStack {
                            LivePhaseOrMachine(
                                attributes: context.attributes,
                                state: context.state
                            )
                            Spacer()
                            LiveActivityTime(state: context.state)
                        }
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        LiveProgressBar(state: context.state)
                    }
                }
            } compactLeading: {
                LiveStatusIcon(state: context.state, size: 18)
            } compactTrailing: {
                LiveProgressText(state: context.state)
                    .font(.caption.monospacedDigit().bold())
            } minimal: {
                LiveStatusIcon(state: context.state, size: 16)
            }
            .widgetURL(deepLink(runID: context.attributes.runID))
            .keylineTint(statusStyle(context.state).color)
        }
    }

    private func deepLink(runID: String) -> URL? {
        URL(string: "runbuoy://runs/\(runID)")
    }
}

struct RunLockScreenView: View {
    let attributes: RunActivityAttributes
    let state: RunActivityAttributes.ContentState

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 10) {
                LiveStatusIcon(state: state, size: 26)
                Text(attributes.title)
                    .font(.headline)
                    .lineLimit(1)
                Spacer(minLength: 6)
                LiveProgressText(state: state)
                    .font(.headline.monospacedDigit())
            }
            LiveProgressBar(state: state)
            HStack {
                LivePhaseOrMachine(attributes: attributes, state: state)
                Spacer()
                LiveActivityTime(state: state)
            }
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .padding()
        .accessibilityElement(children: .combine)
        .accessibilityLabel(statusStyle(state).title)
        .accessibilityValue(statusStyle(state).accessibilityValue(state: state))
    }
}

private struct LiveStatusIcon: View {
    let state: RunActivityAttributes.ContentState
    let size: CGFloat

    var body: some View {
        Image(systemName: statusStyle(state).symbol)
            .font(.system(size: size, weight: .semibold))
            .foregroundStyle(statusStyle(state).color)
            .accessibilityLabel(statusStyle(state).title)
    }
}

private struct LiveProgressText: View {
    let state: RunActivityAttributes.ContentState

    var body: some View {
        if isTerminal(state) {
            Text(state.endedAt ?? state.updatedAt, style: .relative)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
                .accessibilityLabel("widget.terminal_time")
        } else if state.progressKind == "determinate", let progress = state.progress {
            Text(min(max(progress, 0), 1), format: .percent.precision(.fractionLength(0)))
        } else if state.attentionStatus == "WARNING" || state.attentionStatus == "ACTION_REQUIRED" {
            Image(systemName: "exclamationmark.triangle.fill")
                .accessibilityLabel("widget.attention")
        } else {
            Text(state.updatedAt, style: .timer)
                .accessibilityLabel("widget.last_update")
        }
    }
}

private struct LivePhaseOrMachine: View {
    let attributes: RunActivityAttributes
    let state: RunActivityAttributes.ContentState

    var body: some View {
        if let phase = state.phase, !phase.isEmpty {
            Text(phase)
        } else {
            Text(attributes.machineName)
        }
    }
}

private struct LiveActivityTime: View {
    let state: RunActivityAttributes.ContentState

    var body: some View {
        HStack(spacing: 4) {
            if isTerminal(state) {
                Image(systemName: statusStyle(state).symbol)
                    .foregroundStyle(statusStyle(state).color)
                    .accessibilityHidden(true)
                Text(state.endedAt ?? state.updatedAt, style: .relative)
            } else {
                Image(systemName: "arrow.clockwise")
                    .accessibilityHidden(true)
                Text(state.updatedAt, style: .timer)
            }
        }
        .monospacedDigit()
        .lineLimit(1)
        .accessibilityElement(children: .combine)
        .accessibilityLabel(
            isTerminal(state)
                ? Text("widget.terminal_time")
                : Text("widget.last_update")
        )
    }
}

private struct LiveProgressBar: View {
    let state: RunActivityAttributes.ContentState

    var body: some View {
        if state.progressKind == "determinate", let progress = state.progress {
            ProgressView(value: min(max(progress, 0), 1))
                .tint(statusStyle(state).color)
                .accessibilityLabel("widget.progress")
                .accessibilityValue(Text(progress, format: .percent))
        } else {
            HStack(spacing: 7) {
                Image(systemName: "ellipsis")
                    .accessibilityHidden(true)
                Text("progress.indeterminate")
                    .font(.caption)
            }
            .foregroundStyle(.secondary)
        }
    }
}

private struct LiveStatusStyle {
    let title: LocalizedStringKey
    let symbol: String
    let color: Color

    func accessibilityValue(state: RunActivityAttributes.ContentState) -> String {
        if let progress = state.progress, state.progressKind == "determinate" {
            return progress.formatted(.percent.precision(.fractionLength(0)))
        }
        return state.phase ?? state.executionStatus
    }
}

private func statusStyle(_ state: RunActivityAttributes.ContentState) -> LiveStatusStyle {
    switch state.executionStatus {
    case "SUCCEEDED":
        return LiveStatusStyle(title: "status.succeeded", symbol: "checkmark.circle.fill", color: .green)
    case "FAILED":
        return LiveStatusStyle(title: "status.failed", symbol: "xmark.octagon.fill", color: .red)
    case "CANCELLED":
        return LiveStatusStyle(title: "status.cancelled", symbol: "minus.circle.fill", color: .orange)
    case "LOST":
        return LiveStatusStyle(title: "status.lost", symbol: "questionmark.diamond.fill", color: .orange)
    default:
        break
    }
    if state.attentionStatus == "ACTION_REQUIRED" {
        return LiveStatusStyle(
            title: "attention.action_required",
            symbol: "exclamationmark.bubble.fill",
            color: .red
        )
    }
    if state.attentionStatus == "WARNING" {
        return LiveStatusStyle(
            title: "attention.warning",
            symbol: "exclamationmark.triangle.fill",
            color: .orange
        )
    }
    if state.healthStatus == "OFFLINE" {
        return LiveStatusStyle(title: "health.offline", symbol: "wifi.slash", color: .secondary)
    }
    switch state.executionStatus {
    case "STARTING":
        return LiveStatusStyle(title: "status.starting", symbol: "hourglass", color: .blue)
    default:
        return LiveStatusStyle(title: "status.running", symbol: "waveform.path.ecg", color: .blue)
    }
}

private func isTerminal(_ state: RunActivityAttributes.ContentState) -> Bool {
    switch state.executionStatus {
    case "SUCCEEDED", "FAILED", "CANCELLED", "LOST":
        true
    default:
        false
    }
}

private enum WidgetPreviewFixtures {
    static let attributes = RunActivityAttributes(
        runID: "018f0d8a-8c0a-7000-8000-000000000001",
        title: "Gurobi experiment",
        machineName: "Mac Studio"
    )

    static func state(
        execution: String = "RUNNING",
        health: String = "HEALTHY",
        attention: String = "NONE",
        progress: Double? = 0.72,
        phase: String? = "Optimizing"
    ) -> RunActivityAttributes.ContentState {
        .init(
            sequence: 42,
            executionStatus: execution,
            healthStatus: health,
            attentionStatus: attention,
            progressKind: progress == nil ? "indeterminate" : "determinate",
            progress: progress,
            current: progress.map { $0 * 100 },
            total: progress == nil ? nil : 100,
            phase: phase,
            message: nil,
            startedAt: Date().addingTimeInterval(-620),
            updatedAt: Date(),
            endedAt: isTerminalExecution(execution) ? Date().addingTimeInterval(-125) : nil,
            estimatedEndAt: progress == nil ? nil : Date().addingTimeInterval(240),
            exitCode: execution == "FAILED" ? 1 : nil
        )
    }

    private static func isTerminalExecution(_ execution: String) -> Bool {
        switch execution {
        case "SUCCEEDED", "FAILED", "CANCELLED", "LOST":
            true
        default:
            false
        }
    }
}

#Preview("Determinate") {
    RunLockScreenView(
        attributes: WidgetPreviewFixtures.attributes,
        state: WidgetPreviewFixtures.state()
    )
    .padding()
}

#Preview("Indeterminate") {
    RunLockScreenView(
        attributes: WidgetPreviewFixtures.attributes,
        state: WidgetPreviewFixtures.state(progress: nil, phase: "Preparing data")
    )
    .padding()
}

#Preview("Success") {
    RunLockScreenView(
        attributes: WidgetPreviewFixtures.attributes,
        state: WidgetPreviewFixtures.state(execution: "SUCCEEDED", progress: 1, phase: "Completed")
    )
    .padding()
}

#Preview("Failure and attention") {
    RunLockScreenView(
        attributes: WidgetPreviewFixtures.attributes,
        state: WidgetPreviewFixtures.state(
            execution: "FAILED",
            attention: "ACTION_REQUIRED",
            progress: nil,
            phase: "Build failed"
        )
    )
    .padding()
}

#Preview("Offline · 简体中文 · 大字体") {
    RunLockScreenView(
        attributes: RunActivityAttributes(
            runID: WidgetPreviewFixtures.attributes.runID,
            title: "用于验证超长简体中文标题换行的优化实验",
            machineName: "上海实验室的 Mac Studio 工作站"
        ),
        state: WidgetPreviewFixtures.state(health: "OFFLINE", progress: nil, phase: "等待电脑恢复连接")
    )
    .padding()
    .environment(\.locale, Locale(identifier: "zh-Hans"))
    .environment(\.dynamicTypeSize, .accessibility3)
}
