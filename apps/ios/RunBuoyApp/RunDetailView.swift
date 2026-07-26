import SwiftUI
import UIKit

struct RunDetailView: View {
    let runID: UUID
    @Environment(RunBuoyStore.self) private var store
    @State private var detail: RunDetail?
    @State private var errorMessage: String?

    var body: some View {
        Group {
            if let detail {
                RunDetailContent(detail: detail)
            } else if let cached = store.runs.first(where: { $0.id == runID }) {
                RunDetailContent(detail: RunDetail(run: cached, feed: []))
                    .overlay(alignment: .bottom) {
                        if let errorMessage {
                            OfflineBanner(message: errorMessage)
                                .padding()
                        }
                    }
            } else if let errorMessage {
                ContentUnavailableView {
                    Label("run.unavailable", systemImage: "exclamationmark.icloud")
                } description: {
                    Text(errorMessage)
                }
            } else {
                ProgressView("run.loading")
            }
        }
        .navigationTitle("run.detail_title")
        .navigationBarTitleDisplayMode(.inline)
        .task(id: runID) { await load() }
    }

    private func load() async {
        do {
            detail = try await store.detail(for: runID)
            errorMessage = nil
        } catch is CancellationError {
            return
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct RunDetailContent: View {
    let detail: RunDetail
    @AppStorage("runbuoy.safe-messages-enabled") private var safeMessagesEnabled = true

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 14) {
                    Text(detail.run.title)
                        .font(.title2.bold())
                        .fixedSize(horizontal: false, vertical: true)
                    Label(detail.run.machineName, systemImage: "desktopcomputer")
                        .foregroundStyle(.secondary)
                    HStack {
                        StatusBadge(presentation: detail.run.executionStatus.presentation)
                        StatusBadge(presentation: detail.run.healthStatus.presentation)
                    }
                    if detail.run.attentionStatus != .none {
                        StatusBadge(presentation: detail.run.attentionStatus.presentation)
                    }
                    RunProgressView(progress: detail.run.progress, phase: detail.run.phase)
                }
                .padding(.vertical, 8)
            }

            Section("run.timeline") {
                LabeledContent("run.elapsed") {
                    elapsedView
                }
                if let estimate = detail.run.estimatedEndAt {
                    LabeledContent("run.explicit_eta") {
                        Text(estimate, format: .dateTime.hour().minute())
                    }
                }
                LabeledContent("run.started") {
                    Text(detail.run.startedAt, format: .dateTime)
                }
                LabeledContent("run.updated") {
                    Text(detail.run.updatedAt, format: .dateTime)
                }
                if let ended = detail.run.endedAt {
                    LabeledContent("run.ended") {
                        Text(ended, format: .dateTime)
                    }
                }
                if let exitCode = detail.run.exitCode {
                    LabeledContent("run.exit_code", value: exitCode.formatted())
                }
            }

            if safeMessagesEnabled, let message = detail.run.safeMessage, !message.isEmpty {
                Section("run.safe_message") {
                    Text(message)
                        .textSelection(.enabled)
                    Button {
                        UIPasteboard.general.string = message
                    } label: {
                        Label("run.copy_message", systemImage: "doc.on.doc")
                    }
                }
            }

            if !detail.feed.isEmpty {
                Section("run.feed") {
                    ForEach(detail.feed.sorted { $0.sequence < $1.sequence }) { event in
                        RunFeedRow(event: event)
                    }
                }
            }

            if let lines = detail.run.safeLogTail, !lines.isEmpty {
                Section {
                    ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                        Text(line)
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
                Button {
                    UIPasteboard.general.string = detail.run.id.uuidString.lowercased()
                } label: {
                    Label("run.copy_id", systemImage: "doc.on.doc")
                }
                ShareLink(item: shareSummary) {
                    Label("run.share_summary", systemImage: "square.and.arrow.up")
                }
            }
        }
        .listStyle(.insetGrouped)
    }

    @ViewBuilder
    private var elapsedView: some View {
        let end = detail.run.endedAt ?? Date()
        Text(elapsedString(from: detail.run.startedAt, to: max(end, detail.run.startedAt)))
            .monospacedDigit()
    }

    private func elapsedString(from start: Date, to end: Date) -> String {
        let formatter = DateComponentsFormatter()
        formatter.allowedUnits = end.timeIntervalSince(start) >= 3600
            ? [.hour, .minute, .second]
            : [.minute, .second]
        formatter.unitsStyle = .abbreviated
        return formatter.string(from: start, to: end) ?? "—"
    }

    private var shareSummary: String {
        var lines = [
            detail.run.title,
            detail.run.machineName,
            detail.run.executionStatus.rawValue
        ]
        if let safeMessage = detail.run.safeMessage {
            lines.append(safeMessage)
        }
        return lines.joined(separator: "\n")
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
