import SwiftUI
import UIKit

struct RunDetailView: View {
    let runID: UUID
    @Environment(RunBuoyStore.self) private var store
    @State private var detail: RunDetail?
    @State private var errorMessage: String?

    private var presentedDetail: RunDetail? {
        guard let detail else { return nil }
        guard let latestSnapshot = store.runs.first(where: { $0.id == runID }),
              latestSnapshot.sequence >= detail.run.sequence
        else {
            return detail
        }
        return RunDetail(run: latestSnapshot, feed: detail.feed)
    }

    var body: some View {
        ZStack {
            Color.clear
            if let detail = presentedDetail {
                RunDetailContent(detail: detail)
                    .overlay(alignment: .top) {
                        refreshErrorBanner
                    }
            } else if let cached = store.runs.first(where: { $0.id == runID }) {
                RunDetailContent(detail: RunDetail(run: cached, feed: []))
                    .overlay(alignment: .top) {
                        refreshErrorBanner
                    }
            } else if let errorMessage {
                List {
                    ContentUnavailableView {
                        Label("run.unavailable", systemImage: "exclamationmark.icloud")
                    } description: {
                        Text(errorMessage)
                    }
                    .listRowBackground(Color.clear)
                    .listRowSeparator(.hidden)
                }
                .listStyle(.plain)
            } else {
                ProgressView("run.loading")
            }
        }
        .accessibilityIdentifier("screen.runDetail")
        .navigationTitle("run.detail_title")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar(.hidden, for: .tabBar)
        .task(id: runID) { await load() }
        .refreshable { await load() }
    }

    private func load() async {
        do {
            let loadedDetail = try await store.detail(for: runID)
            guard !Task.isCancelled else { return }
            if let detail, loadedDetail.run.sequence < detail.run.sequence {
                return
            }
            detail = loadedDetail
            errorMessage = nil
        } catch is CancellationError {
            return
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @ViewBuilder
    private var refreshErrorBanner: some View {
        if let errorMessage {
            OfflineBanner(message: errorMessage)
                .padding()
        }
    }
}

struct RunDetailContent: View {
    let detail: RunDetail
    private let orderedFeed: [RunFeedEvent]
    private let safeLogLines: [SafeLogLine]
    @AppStorage("runbuoy.safe-messages-enabled") private var safeMessagesEnabled = true

    init(detail: RunDetail) {
        self.detail = detail
        orderedFeed = detail.feed.sorted { $0.sequence < $1.sequence }
        safeLogLines = (detail.run.safeLogTail ?? []).enumerated().map {
            SafeLogLine(id: $0.offset, text: $0.element)
        }
    }

    var body: some View {
        List {
            RunOverviewSection(run: detail.run)

            Section("run.timeline") {
                DetailValueRow("run.elapsed") {
                    RunElapsedView(
                        startedAt: detail.run.startedAt,
                        endedAt: detail.run.endedAt
                    )
                }
                if let estimate = detail.run.estimatedEndAt {
                    DetailValueRow("run.explicit_eta") {
                        Text(estimate, format: .dateTime.hour().minute())
                    }
                }
                DetailValueRow("run.started") {
                    Text(detail.run.startedAt, format: .dateTime)
                }
                DetailValueRow("run.updated") {
                    Text(detail.run.updatedAt, format: .dateTime)
                }
                if let ended = detail.run.endedAt {
                    DetailValueRow("run.ended") {
                        Text(ended, format: .dateTime)
                    }
                }
                if let exitCode = detail.run.exitCode {
                    DetailValueRow("run.exit_code") {
                        Text(exitCode, format: .number)
                    }
                }
            }

            if safeMessagesEnabled, let message = detail.run.safeMessage, !message.isEmpty {
                Section("run.safe_message") {
                    Text(message)
                        .textSelection(.enabled)
                    Button(action: copySafeMessage) {
                        Label("run.copy_message", systemImage: "doc.on.doc")
                    }
                    .tint(.primary)
                }
            }

            if !orderedFeed.isEmpty {
                Section("run.feed") {
                    ForEach(orderedFeed) { event in
                        RunFeedRow(event: event)
                    }
                }
            }

            if !safeLogLines.isEmpty {
                Section {
                    ForEach(safeLogLines) { line in
                        Text(line.text)
                            .font(.system(.caption, design: .monospaced))
                            .textSelection(.enabled)
                    }
                } header: {
                    Text("run.safe_log_tail")
                } footer: {
                    Text("run.safe_log_tail_notice")
                }
            }

            Section("run.identifier") {
                Text(detail.run.id.uuidString.lowercased())
                    .font(.caption.monospaced())
                    .textSelection(.enabled)
            }
        }
        .listStyle(.insetGrouped)
        .safeAreaInset(edge: .bottom) {
            RunDetailActionBar(run: detail.run)
        }
    }

    private func copySafeMessage() {
        guard let safeMessage = detail.run.safeMessage else { return }
        UIPasteboard.general.string = safeMessage
    }
}

private struct SafeLogLine: Identifiable {
    let id: Int
    let text: String
}

private struct DetailValueRow<Value: View>: View {
    let title: LocalizedStringKey
    @ViewBuilder let value: () -> Value
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    init(
        _ title: LocalizedStringKey,
        @ViewBuilder value: @escaping () -> Value
    ) {
        self.title = title
        self.value = value
    }

    var body: some View {
        Group {
            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 4) {
                    titleLabel
                    valueLabel
                }
            } else {
                HStack(alignment: .firstTextBaseline, spacing: 12) {
                    titleLabel
                    Spacer(minLength: 8)
                    valueLabel
                }
            }
        }
        .accessibilityElement(children: .combine)
    }

    private var titleLabel: some View {
        Text(title)
            .fixedSize(horizontal: false, vertical: true)
    }

    private var valueLabel: some View {
        value()
            .foregroundStyle(.primary)
            .fixedSize(horizontal: false, vertical: true)
            .multilineTextAlignment(dynamicTypeSize.isAccessibilitySize ? .leading : .trailing)
    }
}

private struct RunOverviewSection: View {
    let run: RunSnapshot

    var body: some View {
        Section {
            VStack(alignment: .leading, spacing: 14) {
                Text(run.title)
                    .font(.title2.bold())
                    .fixedSize(horizontal: false, vertical: true)
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    MachineIconImage(machineID: run.machineID)
                        .accessibilityHidden(true)
                    Text(run.machineName)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .foregroundStyle(.primary)
                HStack {
                    StatusBadge(presentation: run.executionStatus.presentation)
                    StatusBadge(presentation: run.healthStatus.presentation)
                }
                if run.attentionStatus != .none {
                    StatusBadge(presentation: run.attentionStatus.presentation)
                }
                RunProgressView(
                    progress: run.progress,
                    phase: run.phase,
                    showsIndeterminate: run.executionStatus.isActive,
                    emphasis: .prominent,
                    tint: run.executionStatus.progressTint
                )
            }
            .padding(.vertical, 8)
        }
    }
}

private struct RunElapsedView: View {
    let startedAt: Date
    let endedAt: Date?

    var body: some View {
        if let endedAt {
            durationText(to: endedAt)
        } else {
            TimelineView(.periodic(from: .now, by: 1)) { context in
                durationText(to: context.date)
            }
        }
    }

    private func durationText(to end: Date) -> some View {
        Text(RunDurationText.string(from: startedAt, to: end))
            .monospacedDigit()
            .foregroundStyle(.primary)
    }
}

private struct RunDetailActionBar: View {
    let run: RunSnapshot

    var body: some View {
        GlassEffectContainer(spacing: 12) {
            HStack(spacing: 12) {
                Spacer(minLength: 0)

                Button(action: copyID) {
                    Image(systemName: "doc.on.doc")
                        .frame(minWidth: 44, minHeight: 44)
                        .contentShape(Circle())
                }
                .buttonStyle(.glass)
                .buttonBorderShape(.circle)
                .accessibilityLabel("run.copy_id")

                ShareLink(item: shareSummary) {
                    Image(systemName: "square.and.arrow.up")
                        .frame(minWidth: 44, minHeight: 44)
                        .contentShape(Circle())
                }
                .buttonStyle(.glassProminent)
                .buttonBorderShape(.circle)
                .accessibilityLabel("run.share_summary")
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
    }

    private var shareSummary: String {
        var lines = [run.title, run.machineName, run.executionStatus.rawValue]
        if let safeMessage = run.safeMessage {
            lines.append(safeMessage)
        }
        return lines.joined(separator: "\n")
    }

    private func copyID() {
        UIPasteboard.general.string = run.id.uuidString.lowercased()
    }
}

struct RunFeedRow: View {
    let event: RunFeedEvent

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Text(event.occurredAt, format: .dateTime.hour().minute())
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)
                .accessibilityLabel(event.occurredAt.formatted(date: .omitted, time: .shortened))
            Image(systemName: symbol)
                .foregroundStyle(.tint)
                .frame(width: 18)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 3) {
                Text(eventTitle)
                    .font(.subheadline.weight(.semibold))
                if let phase = event.phase {
                    Text(phase)
                }
                if let message = event.message {
                    Text(message)
                        .foregroundStyle(.secondary)
                }
                if let progress = event.progress, let fraction = progress.boundedFraction {
                    Text(fraction, format: .percent.precision(.fractionLength(0)))
                        .font(.caption.monospacedDigit())
                }
            }
            .font(.subheadline)
        }
        .accessibilityElement(children: .combine)
    }

    private var eventTitle: LocalizedStringKey {
        switch event.type {
        case "run.created": "event.created"
        case "run.starting": "event.starting"
        case "run.started": "event.started"
        case "run.progress": "event.progress"
        case "run.phase_changed": "event.phase"
        case "run.message": "event.message"
        case "run.attention_required": "event.attention"
        case "run.heartbeat": "event.heartbeat"
        case "run.succeeded": "event.succeeded"
        case "run.failed": "event.failed"
        case "run.cancelled": "event.cancelled"
        case "run.lost": "event.lost"
        default: "event.updated"
        }
    }

    private var symbol: String {
        switch event.type {
        case "run.succeeded": "checkmark.circle.fill"
        case "run.failed": "xmark.octagon.fill"
        case "run.attention_required": "exclamationmark.triangle.fill"
        case "run.progress": "chart.bar.fill"
        case "run.phase_changed": "flag.fill"
        case "run.message": "text.bubble.fill"
        default: "circle.fill"
        }
    }
}

#Preview("Long English") {
    NavigationStack {
        RunDetailContent(detail: PreviewFixtures.longEnglishDetail)
    }
}

#Preview("简体中文 · 辅助功能字号") {
    NavigationStack {
        RunDetailContent(detail: PreviewFixtures.longChineseDetail)
    }
    .environment(\.locale, Locale(identifier: "zh-Hans"))
    .environment(\.dynamicTypeSize, .accessibility4)
}
