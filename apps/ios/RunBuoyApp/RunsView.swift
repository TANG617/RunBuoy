import SwiftUI

struct ActiveRunsView: View {
    @Environment(RunBuoyStore.self) private var store

    private var isEmpty: Bool {
        store.activeRunModels.isEmpty
    }

    var body: some View {
        List {
            if case .offline(let message) = store.state {
                OfflineBanner(message: message)
                    .listRowSeparator(.hidden)
            }

            if !store.activeRunModels.isEmpty {
                Section("runs.active") {
                    ForEach(store.activeRunModels) { model in
                        NavigationLink(value: AppRoute.runDetail(model.id)) {
                            RunRow(model: model)
                        }
                    }
                }
            }

            if isEmpty, store.state == .loading {
                RunLoadingRows()
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle("runs.active")
        .overlay {
            if isEmpty, store.state != .loading {
                ActiveRunsEmptyState(state: store.state)
                    .allowsHitTesting(false)
            }
        }
        .refreshable { await reload() }
        .task { await loadIfNeeded() }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button(action: refresh) {
                    Label("common.refresh", systemImage: "arrow.clockwise")
                }
                .disabled(store.state == .loading)
            }
        }
    }

    private func refresh() {
        Task { await reload() }
    }

    private func loadIfNeeded() async {
        guard store.state == .idle else { return }
        await store.refresh()
    }

    private func reload() async {
        await store.refresh()
    }
}

struct RunHistoryView: View {
    @Environment(RunBuoyStore.self) private var store
    @AppStorage("runbuoy.safe-messages-enabled") private var safeMessagesEnabled = true

    private var showsMessages: Bool {
        safeMessagesEnabled && !store.messages.isEmpty
    }

    private var isEmpty: Bool {
        store.historyRunModels.isEmpty && !showsMessages
    }

    var body: some View {
        List {
            if case .offline(let message) = store.state {
                OfflineBanner(message: message)
                    .listRowSeparator(.hidden)
            }

            if !store.historyRunModels.isEmpty {
                Section("runs.recent") {
                    ForEach(store.historyRunModels) { model in
                        NavigationLink(value: AppRoute.runDetail(model.id)) {
                            RunRow(model: model)
                        }
                    }
                }
            }

            if showsMessages {
                Section("runs.messages") {
                    ForEach(store.messages) { message in
                        RichMessageRow(message: message)
                    }
                }
            }

            if isEmpty, store.state == .loading {
                RunLoadingRows()
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle("history.title")
        .overlay {
            if isEmpty, store.state != .loading {
                HistoryEmptyState(state: store.state)
                    .allowsHitTesting(false)
            }
        }
        .refreshable { await reload() }
        .task { await loadIfNeeded() }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button(action: refresh) {
                    Label("common.refresh", systemImage: "arrow.clockwise")
                }
                .disabled(store.state == .loading)
            }
        }
    }

    private func refresh() {
        Task { await reload() }
    }

    private func loadIfNeeded() async {
        guard store.state == .idle else { return }
        await store.refresh()
    }

    private func reload() async {
        await store.refresh()
    }
}

private struct RunLoadingRows: View {
    private enum Placeholder: String, CaseIterable, Identifiable {
        case first
        case second
        case third

        var id: String { rawValue }
    }

    var body: some View {
        Section {
            ForEach(Placeholder.allCases) { _ in
                RunLoadingRow()
                    .redacted(reason: .placeholder)
                    .allowsHitTesting(false)
            }
        }
        .accessibilityLabel("runs.loading")
    }
}

private struct RunLoadingRow: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("A run title appears here")
                    .font(.headline)
                Spacer()
                Text("Running")
                    .font(.caption.weight(.semibold))
            }
            Label("Machine", systemImage: "desktopcomputer")
                .font(.subheadline)
            ProgressView(value: 0.4)
            Text("Working")
                .font(.subheadline.weight(.medium))
        }
        .padding(.vertical, 6)
    }
}

private struct ActiveRunsEmptyState: View {
    let state: RunBuoyStore.LoadState

    var body: some View {
        ContentUnavailableView {
            Label(title, systemImage: symbol)
        } description: {
            Text(description)
        }
        .padding()
    }

    private var title: LocalizedStringKey {
        if case .failed = state {
            return "runs.unavailable"
        }
        return "runs.active_empty"
    }

    private var description: LocalizedStringKey {
        if case .failed = state {
            return "runs.pull_to_refresh"
        }
        return "runs.active_empty_description"
    }

    private var symbol: String {
        if case .failed = state {
            return "exclamationmark.icloud"
        }
        return "checkmark.circle"
    }
}

private struct HistoryEmptyState: View {
    let state: RunBuoyStore.LoadState

    var body: some View {
        ContentUnavailableView {
            Label(title, systemImage: symbol)
        } description: {
            Text(description)
        }
        .padding()
    }

    private var title: LocalizedStringKey {
        if case .failed = state {
            return "runs.unavailable"
        }
        return "history.empty"
    }

    private var description: LocalizedStringKey {
        if case .failed = state {
            return "runs.pull_to_refresh"
        }
        return "history.empty_description"
    }

    private var symbol: String {
        if case .failed = state {
            return "exclamationmark.icloud"
        }
        return "clock.arrow.circlepath"
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

#Preview("Active Runs · Light") {
    NavigationStack { ActiveRunsView() }
        .environment(PreviewFixtures.store())
}

#Preview("History · Dark · Large Type") {
    NavigationStack { RunHistoryView() }
        .environment(PreviewFixtures.store())
        .preferredColorScheme(.dark)
        .environment(\.dynamicTypeSize, .accessibility3)
}
