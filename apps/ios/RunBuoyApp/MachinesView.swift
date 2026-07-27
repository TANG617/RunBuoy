import SwiftUI

private enum MachinesSheet: String, Identifiable {
    case pairMachine

    var id: String { rawValue }
}

struct MachinesView: View {
    @Environment(RunBuoyStore.self) private var store
    @State private var presentedSheet: MachinesSheet?

    var body: some View {
        List {
            ForEach(store.machines) { machine in
                NavigationLink(value: AppRoute.machine(machine.id)) {
                    MachineRow(machine: machine)
                }
            }
        }
        .listStyle(.insetGrouped)
        .navigationTitle("machines.title")
        .overlay {
            if store.machines.isEmpty {
                MachinesEmptyState(isLoading: store.state == .loading)
                    .allowsHitTesting(false)
            }
        }
        .refreshable { await reload() }
        .task { await loadIfNeeded() }
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                Button(action: refresh) {
                    Label("common.refresh", systemImage: "arrow.clockwise")
                }
                .disabled(store.state == .loading)

                Button(action: showPairing) {
                    Label("settings.pair_machine", systemImage: "qrcode.viewfinder")
                }
            }
        }
        .sheet(item: $presentedSheet) { sheet in
            switch sheet {
            case .pairMachine:
                PairMachineSheet()
            }
        }
    }

    private func showPairing() {
        presentedSheet = .pairMachine
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

private struct MachinesEmptyState: View {
    let isLoading: Bool

    var body: some View {
        Group {
            if isLoading {
                ProgressView("machines.loading")
            } else {
                ContentUnavailableView {
                    Label("machines.empty", systemImage: "desktopcomputer")
                } description: {
                    Text("machines.empty_description")
                }
            }
        }
        .padding()
    }
}

private struct PairMachineSheet: View {
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            PairMachineView()
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("common.close", action: dismiss.callAsFunction)
                    }
                }
        }
    }
}

struct MachineRow: View {
    let machine: MachineSnapshot

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: machineSymbol)
                .font(.title2)
                .foregroundStyle(machine.isSubscribed ? Color.accentColor : .secondary)
                .frame(width: 34)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 4) {
                Text(localLabel)
                    .font(.headline)
                Text("\(machine.platform) · \(machine.cliVersion)")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                Label {
                    Text(machine.lastSeenAt, format: .relative(presentation: .named))
                } icon: {
                    Image(systemName: machine.isSubscribed ? "bell.fill" : "bell.slash")
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
    }

    private var machineSymbol: String {
        machine.isSubscribed
            ? "desktopcomputer"
            : "desktopcomputer.trianglebadge.exclamationmark"
    }

    private var localLabel: String {
        UserDefaults.standard.string(forKey: labelKey) ?? machine.displayName
    }

    private var labelKey: String {
        "runbuoy.machine-label.\(machine.id)"
    }
}

struct MachineDetailView: View {
    let machineID: String
    @Environment(RunBuoyStore.self) private var store

    var body: some View {
        ZStack {
            Color.clear
            if let machine = store.machines.first(where: { $0.id == machineID }) {
                MachineDetailContent(machine: machine)
            } else {
                ContentUnavailableView("machines.not_found", systemImage: "desktopcomputer")
            }
        }
    }
}

private struct MachineDetailContent: View {
    @Environment(RunBuoyStore.self) private var store

    let machine: MachineSnapshot
    @State private var localLabel: String
    @State private var notice: LocalizedStringKey?

    init(machine: MachineSnapshot) {
        self.machine = machine
        _localLabel = State(
            initialValue: UserDefaults.standard.string(
                forKey: "runbuoy.machine-label.\(machine.id)"
            ) ?? machine.displayName
        )
    }

    var body: some View {
        Form {
            Section("machine.identity") {
                TextField("machine.local_label", text: $localLabel)
                    .textInputAutocapitalization(.words)
                    .accessibilityHint("machine.local_label_hint")
                Button("machine.save_local_label", action: saveLocalLabel)
                LabeledContent("machine.platform", value: machine.platform)
                if let architecture = machine.architecture {
                    LabeledContent("machine.architecture", value: architecture)
                }
                LabeledContent("machine.cli_version", value: machine.cliVersion)
                LabeledContent("machine.last_seen") {
                    Text(machine.lastSeenAt, format: .dateTime)
                }
                LabeledContent("machine.paired") {
                    Text(machine.pairedAt, format: .dateTime)
                }
            }

            Section {
                if machine.isSubscribed, machine.subscriptionID != nil {
                    Button(
                        "machine.stop_receiving",
                        role: .destructive,
                        action: stopReceiving
                    )
                }
                Button(
                    "machine.remove_pairing",
                    role: .destructive,
                    action: removePairing
                )
            } footer: {
                Text("machine.removal_explanation")
            }

            if let notice {
                Section {
                    Label(notice, systemImage: "checkmark.circle")
                        .foregroundStyle(.secondary)
                }
            }
        }
        .navigationTitle(localLabel.isEmpty ? machine.displayName : localLabel)
        .navigationBarTitleDisplayMode(.inline)
    }

    private var labelKey: String {
        "runbuoy.machine-label.\(machine.id)"
    }

    private func saveLocalLabel() {
        let value = localLabel.trimmingCharacters(in: .whitespacesAndNewlines)
        if value.isEmpty {
            UserDefaults.standard.removeObject(forKey: labelKey)
            localLabel = machine.displayName
        } else {
            UserDefaults.standard.set(value, forKey: labelKey)
            localLabel = value
        }
        notice = "machine.label_saved"
    }

    private func stopReceiving() {
        guard let subscriptionID = machine.subscriptionID else { return }
        Task {
            try? await store.stopReceiving(subscriptionID: subscriptionID)
            notice = "machine.receiving_stopped"
        }
    }

    private func removePairing() {
        Task {
            try? await store.removeLocalPairing(subscriptionID: machine.subscriptionID)
            notice = "machine.pairing_removed"
        }
    }
}

#Preview("Machines") {
    NavigationStack { MachinesView() }
        .environment(PreviewFixtures.store())
}

#Preview("Machine Detail · Large Type") {
    NavigationStack {
        MachineDetailView(machineID: PreviewFixtures.machine.id)
    }
    .environment(PreviewFixtures.store())
    .environment(\.dynamicTypeSize, .accessibility2)
}
