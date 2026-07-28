import Foundation
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
                RefreshButton(
                    isRefreshing: store.state == .loading,
                    action: refresh
                )
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
    @State private var selectedMachineID: String?

    init(initialMachineID: String? = nil) {
        _selectedMachineID = State(initialValue: initialMachineID)
    }

    private var machineOptions: [HistoryMachineOption] {
        HistoryMachineOption.makeOptions(
            machines: store.machines,
            runs: store.historyRunModels.map(\.snapshot),
            messages: store.messages
        )
    }

    private var machineOptionIDs: [String] {
        machineOptions.map(\.id)
    }

    private var selectedMachineName: String? {
        guard let selectedMachineID else { return nil }
        return machineOptions.first(where: { $0.id == selectedMachineID })?.name
    }

    private var contentFilter: HistoryContentFilter {
        HistoryContentFilter(machineID: selectedMachineID)
    }

    private var filteredRunModels: [RunSummaryModel] {
        store.historyRunModels.filter {
            contentFilter.includes(machineID: $0.snapshot.machineID)
        }
    }

    private var filteredMessages: [RichMessage] {
        guard safeMessagesEnabled else { return [] }
        return store.messages.filter {
            contentFilter.includes(machineID: $0.machineID)
        }
    }

    private var isEmpty: Bool {
        filteredRunModels.isEmpty && filteredMessages.isEmpty
    }

    var body: some View {
        List {
            if case .offline(let message) = store.state {
                OfflineBanner(message: message)
                    .listRowSeparator(.hidden)
            }

            if !filteredRunModels.isEmpty {
                Section("runs.recent") {
                    ForEach(filteredRunModels) { model in
                        NavigationLink(value: AppRoute.runDetail(model.id)) {
                            RunRow(model: model)
                        }
                    }
                }
            }

            if !filteredMessages.isEmpty {
                Section("runs.messages") {
                    ForEach(filteredMessages) { message in
                        RichMessageRow(message: message)
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle("history.title")
        .navigationBarTitleDisplayMode(.inline)
        .overlay {
            if isEmpty, store.state != .loading {
                HistoryEmptyState(
                    state: store.state,
                    machineID: selectedMachineID,
                    machineName: selectedMachineName
                )
                    .allowsHitTesting(false)
            }
        }
        .safeAreaInset(edge: .top, spacing: 0) {
            if !machineOptions.isEmpty {
                VStack(spacing: 0) {
                    HistoryMachineFilterBar(
                        options: machineOptions,
                        selection: $selectedMachineID
                    )
                    Divider()
                }
                .background(.ultraThinMaterial)
            }
        }
        .refreshable { await reload() }
        .task { await loadIfNeeded() }
        .onChange(of: machineOptionIDs) { _, availableIDs in
            guard let selectedMachineID,
                  !availableIDs.contains(selectedMachineID)
            else {
                return
            }
            self.selectedMachineID = nil
        }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                RefreshButton(
                    isRefreshing: store.state == .loading,
                    action: refresh
                )
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

struct HistoryMachineOption: Identifiable, Hashable {
    let id: String
    let name: String

    static func makeOptions(
        machines: [MachineSnapshot],
        runs: [RunSnapshot],
        messages: [RichMessage],
        userDefaults: UserDefaults = .standard
    ) -> [HistoryMachineOption] {
        var serverNamesByID: [String: String] = [:]

        for message in messages {
            guard let machineID = message.machineID, !machineID.isEmpty else { continue }
            serverNamesByID[machineID] = serverNamesByID[machineID] ?? machineID
        }
        for run in runs.reversed() {
            serverNamesByID[run.machineID] = run.machineName
        }
        for machine in machines {
            serverNamesByID[machine.id] = machine.displayName
        }

        return serverNamesByID.map { machineID, serverName in
            HistoryMachineOption(
                id: machineID,
                name: MachineLocalLabel.displayName(
                    machineID: machineID,
                    serverName: serverName,
                    userDefaults: userDefaults
                )
            )
        }
        .sorted { lhs, rhs in
            let comparison = lhs.name.localizedStandardCompare(rhs.name)
            if comparison == .orderedSame {
                return lhs.id < rhs.id
            }
            return comparison == .orderedAscending
        }
    }
}

struct HistoryContentFilter: Equatable {
    let machineID: String?

    func includes(machineID candidateMachineID: String?) -> Bool {
        guard let machineID else { return true }
        return candidateMachineID == machineID
    }
}

private struct HistoryMachineFilterBar: View {
    let options: [HistoryMachineOption]
    @Binding var selection: String?
    @ScaledMetric(relativeTo: .subheadline) private var height = 54

    var body: some View {
        ScrollView(.horizontal) {
            HStack(spacing: 8) {
                filterButton(id: nil) {
                    Text("history.all")
                }
                ForEach(options) { option in
                    filterButton(id: option.id) {
                        Label {
                            Text(option.name)
                        } icon: {
                            MachineIconImage(machineID: option.id)
                        }
                    }
                }
            }
            .padding(.horizontal)
            .padding(.vertical, 8)
        }
        .scrollIndicators(.hidden)
        .frame(height: height)
    }

    private func filterButton<Content: View>(
        id: String?,
        @ViewBuilder label: () -> Content
    ) -> some View {
        let isSelected = selection == id
        return Button {
            selection = id
        } label: {
            label()
                .font(.subheadline.weight(.semibold))
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
                .foregroundStyle(
                    isSelected
                        ? Color(uiColor: .systemBackground)
                        : Color.primary
                )
                .padding(.horizontal, 14)
                .padding(.vertical, 9)
                .background {
                    Capsule()
                        .fill(
                            isSelected
                                ? Color.primary
                                : Color.secondary.opacity(0.16)
                        )
                }
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(isSelected ? .isSelected : [])
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
    let machineID: String?
    let machineName: String?

    var body: some View {
        ContentUnavailableView {
            Label {
                Text(title)
            } icon: {
                if let machineID, !isFailure {
                    MachineIconImage(machineID: machineID)
                } else {
                    Image(systemName: symbol)
                }
            }
        } description: {
            Text(description)
        }
        .padding()
    }

    private var title: String {
        if case .failed = state {
            return String(localized: "runs.unavailable")
        }
        if let machineName {
            return String(
                format: String(localized: "history.filtered_empty"),
                machineName
            )
        }
        return String(localized: "history.empty")
    }

    private var description: String {
        if case .failed = state {
            return String(localized: "runs.pull_to_refresh")
        }
        if machineName != nil {
            return String(localized: "history.filtered_empty_description")
        }
        return String(localized: "history.empty_description")
    }

    private var symbol: String {
        if isFailure {
            return "exclamationmark.icloud"
        }
        return "clock.arrow.circlepath"
    }

    private var isFailure: Bool {
        if case .failed = state {
            return true
        }
        return false
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

#Preview("History · Selected Machine") {
    NavigationStack {
        RunHistoryView(initialMachineID: PreviewFixtures.ciMachine.id)
    }
    .environment(PreviewFixtures.store())
}
