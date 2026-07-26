import SwiftUI

struct RunsView: View {
    @Environment(RunBuoyStore.self) private var store
    @AppStorage("runbuoy.safe-messages-enabled") private var safeMessagesEnabled = true

    var body: some View {
        Group {
            if store.runs.isEmpty && (store.messages.isEmpty || !safeMessagesEnabled) {
                emptyOrLoading
            } else {
                content
            }
        }
        .navigationTitle("runs.title")
        .refreshable { await store.refresh() }
        .task {
            if store.state == .idle {
                await store.refresh()
            }
        }
    }

    private var content: some View {
        List {
            if case .offline(let message) = store.state {
                OfflineBanner(message: message)
                    .listRowSeparator(.hidden)
            }

            if !store.activeRuns.isEmpty {
                Section("runs.active") {
                    ForEach(store.activeRuns) { run in
                        NavigationLink(value: AppRoute.runDetail(run.id)) {
                            RunRow(run: run)
                        }
                    }
                }
            }

            if !store.recentRuns.isEmpty {
                Section("runs.recent") {
                    ForEach(store.recentRuns.prefix(20)) { run in
                        NavigationLink(value: AppRoute.runDetail(run.id)) {
                            RunRow(run: run)
                        }
                    }
                }
            }

            if safeMessagesEnabled, !store.messages.isEmpty {
                Section("runs.messages") {
                    ForEach(store.messages.prefix(10)) { message in
                        RichMessageRow(message: message)
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
    }

    @ViewBuilder
    private var emptyOrLoading: some View {
        switch store.state {
        case .loading:
            List {
                ForEach(0..<4, id: \.self) { _ in
                    RunRow(run: PreviewFixtures.placeholderRun)
                        .redacted(reason: .placeholder)
                }
            }
            .listStyle(.plain)
            .accessibilityLabel("runs.loading")
        case .failed(let message):
            ContentUnavailableView {
                Label("runs.unavailable", systemImage: "exclamationmark.icloud")
            } description: {
                Text(message)
                Text("runs.pull_to_refresh")
            }
        default:
            ContentUnavailableView {
                Label("runs.empty", systemImage: "water.waves")
            } description: {
                Text("runs.empty_description")
            }
        }
    }
}

struct RichMessageRow: View {
    let message: RichMessage

    var body: some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack {
                Image(systemName: messageSymbol)
                    .foregroundStyle(messageColor)
                    .accessibilityHidden(true)
                Text(message.title)
                    .font(.headline)
                Spacer()
                Text(message.createdAt, format: .relative(presentation: .named))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if let subtitle = message.subtitle {
                Text(subtitle)
                    .font(.subheadline.weight(.medium))
            }
            Text(message.body)
                .font(.body)
                .textSelection(.enabled)
            ForEach(message.fields) { field in
                LabeledContent(field.name, value: field.value)
                    .font(.caption)
            }
        }
        .padding(.vertical, 5)
        .accessibilityElement(children: .combine)
    }

    private var messageSymbol: String {
        switch message.level.lowercased() {
        case "success": "checkmark.circle.fill"
        case "warning": "exclamationmark.triangle.fill"
        case "error", "failure": "xmark.octagon.fill"
        default: "info.circle.fill"
        }
    }

    private var messageColor: Color {
        switch message.level.lowercased() {
        case "success": .green
        case "warning": .orange
        case "error", "failure": .red
        default: .blue
        }
    }
}

#Preview("Loaded") {
    NavigationStack { RunsView() }
        .environment(PreviewFixtures.store())
}

#Preview("Large type") {
    NavigationStack { RunsView() }
        .environment(PreviewFixtures.store())
        .environment(\.dynamicTypeSize, .accessibility3)
}
