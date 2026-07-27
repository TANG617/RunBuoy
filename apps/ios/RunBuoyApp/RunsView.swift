import SwiftUI

private enum RunListSheet: String, Identifiable {
    case readOnlyBoundary

    var id: String { rawValue }
}

struct ActiveRunsView: View {
    @Environment(RunBuoyStore.self) private var store
    @State private var presentedSheet: RunListSheet?

    private var isEmpty: Bool {
        store.activeRunModels.isEmpty
    }

    var body: some View {
        List {
            Section {
                RunListToolStrip(
                    isRefreshing: store.state == .loading,
                    onShowReadOnlyInfo: showReadOnlyInfo,
                    onRefresh: refresh
                )
            }
            .listRowBackground(Color.clear)
            .listRowInsets(.init(top: 8, leading: 16, bottom: 8, trailing: 16))

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
        .sheet(item: $presentedSheet) { sheet in
            switch sheet {
            case .readOnlyBoundary:
                ReadOnlyInformationSheet()
            }
        }
    }

    private func showReadOnlyInfo() {
        presentedSheet = .readOnlyBoundary
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

private struct RunListToolStrip: View {
    let isRefreshing: Bool
    let onShowReadOnlyInfo: () -> Void
    let onRefresh: () -> Void
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        GlassEffectContainer(spacing: 12) {
            HStack(spacing: 12) {
                if dynamicTypeSize.isAccessibilitySize {
                    ReadOnlyGlassIcon()
                } else {
                    ReadOnlyGlassLabel()
                }

                Spacer(minLength: 0)

                Button(action: onShowReadOnlyInfo) {
                    Image(systemName: "info")
                        .frame(width: 24, height: 24)
                }
                .buttonStyle(.glass)
                .buttonBorderShape(.circle)
                .accessibilityLabel("runs.read_only_info")

                Button(action: onRefresh) {
                    Group {
                        if isRefreshing {
                            ProgressView()
                                .controlSize(.small)
                        } else {
                            Image(systemName: "arrow.clockwise")
                        }
                    }
                    .frame(width: 24, height: 24)
                }
                .buttonStyle(.glassProminent)
                .buttonBorderShape(.circle)
                .disabled(isRefreshing)
                .accessibilityLabel("common.refresh")
            }
        }
        .accessibilityElement(children: .contain)
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

private struct ReadOnlyInformationSheet: View {
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Label("runs.read_only_flow", systemImage: "arrow.right")
                    Label("runs.no_remote_commands", systemImage: "terminal.fill")
                    Label("runs.full_logs_local", systemImage: "lock.shield.fill")
                }

                Section("settings.live_activities") {
                    Label("runs.live_activity_contents", systemImage: "platter.filled.bottom.iphone")
                }
            }
            .navigationTitle("runs.read_only_info")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("common.done", action: dismiss.callAsFunction)
                }
            }
        }
        .presentationDetents([.medium, .large])
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
