import SwiftUI

private enum MachinesSheet: Identifiable {
    case scanner
    case pairingCode
    case confirmation(PairingCode)

    var id: String {
        switch self {
        case .scanner:
            "scanner"
        case .pairingCode:
            "pairing-code"
        case .confirmation:
            "confirmation"
        }
    }
}

struct MachinesView: View {
    @Environment(RunBuoyStore.self) private var store
    @State private var presentedSheet: MachinesSheet?
    @State private var queuedPairingCode: PairingCode?
    @State private var pairingError: String?

    var body: some View {
        List {
            ForEach(store.machines) { machine in
                NavigationLink(value: AppRoute.machine(machine.id)) {
                    MachineRow(machine: machine)
                }
                .accessibilityIdentifier("machine.row.\(machine.id)")
            }
        }
        .listStyle(.insetGrouped)
        .accessibilityIdentifier("screen.machines")
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
                RefreshButton(
                    isRefreshing: store.state == .loading,
                    action: refresh
                )

                Button(action: showPairingCode) {
                    Label("pairing.enter_code", systemImage: "keyboard")
                }
                .accessibilityIdentifier("machines.enterPairingCode")

                Button(action: showScanner) {
                    Label("pairing.scan_title", systemImage: "qrcode.viewfinder")
                }
                .accessibilityIdentifier("machines.scanPairingCode")
            }
        }
        .sheet(item: $presentedSheet, onDismiss: presentQueuedPairingCode) { sheet in
            switch sheet {
            case .scanner:
                ScannerSheet(onCode: receiveScannedCode)
            case .pairingCode:
                PairMachineSheet(allowsCodeEntry: true)
            case .confirmation(let code):
                PairMachineSheet(
                    initialCode: code,
                    allowsCodeEntry: false
                )
            }
        }
        .alert(
            "pairing.invalid_code_title",
            isPresented: Binding(
                get: { pairingError != nil },
                set: { isPresented in
                    if !isPresented {
                        pairingError = nil
                    }
                }
            )
        ) {
            Button("common.close", role: .cancel) {}
        } message: {
            Text(pairingError ?? "")
        }
    }

    private func showScanner() {
        presentedSheet = .scanner
    }

    private func showPairingCode() {
        presentedSheet = .pairingCode
    }

    private func receiveScannedCode(_ value: String) {
        do {
            queuedPairingCode = try PairingCode.decode(value)
            pairingError = nil
        } catch {
            queuedPairingCode = nil
            pairingError = error.localizedDescription
        }
    }

    private func presentQueuedPairingCode() {
        guard let code = queuedPairingCode else { return }
        queuedPairingCode = nil
        Task { @MainActor in
            await Task.yield()
            presentedSheet = .confirmation(code)
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

private struct MachinesEmptyState: View {
    let isLoading: Bool

    var body: some View {
        Group {
            if isLoading {
                ProgressView("machines.loading")
            } else {
                ContentUnavailableView {
                    Label("machines.empty", systemImage: "desktopcomputer.and.macbook")
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
    var initialCode: PairingCode?
    let allowsCodeEntry: Bool

    init(
        initialCode: PairingCode? = nil,
        allowsCodeEntry: Bool
    ) {
        self.initialCode = initialCode
        self.allowsCodeEntry = allowsCodeEntry
    }

    var body: some View {
        NavigationStack {
            PairMachineView(
                initialCode: initialCode,
                allowsCodeEntry: allowsCodeEntry,
                dismissesOnSuccess: true
            )
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
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        Group {
            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 8) {
                    machineIcon
                    machineMetadata
                }
            } else {
                HStack(spacing: 12) {
                    machineIcon
                    machineMetadata
                }
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
    }

    private var machineIcon: some View {
        MachineIconImage(machineID: machine.id)
            .font(.title2)
            .foregroundStyle(machine.isSubscribed ? Color.accentColor : .secondary)
            .frame(width: 34)
            .overlay(alignment: .bottomTrailing) {
                if !machine.isSubscribed {
                    Image(systemName: "exclamationmark.circle.fill")
                        .font(.caption2)
                        .foregroundStyle(.orange)
                        .background(.background, in: Circle())
                }
            }
            .accessibilityHidden(true)
    }

    private var machineMetadata: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(machine.displayName)
                .font(.headline)
                .lineLimit(nil)
                .fixedSize(horizontal: false, vertical: true)
            Text("\(machine.platform) · \(machine.cliVersion)")
                .font(.subheadline)
                .foregroundStyle(.primary)
                .fixedSize(horizontal: false, vertical: true)
            Label {
                Text(machine.lastSeenAt, format: .relative(presentation: .named))
            } icon: {
                Image(systemName: machine.isSubscribed ? "bell.fill" : "bell.slash")
            }
            .labelStyle(MachineMetadataLabelStyle())
            .font(.caption)
            .foregroundStyle(.primary)
        }
        .fixedSize(horizontal: false, vertical: true)
        .layoutPriority(1)
    }

}

private struct MachineMetadataLabelStyle: LabelStyle {
    func makeBody(configuration: Configuration) -> some View {
        HStack(spacing: 4) {
            configuration.icon
            configuration.title
        }
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
                ContentUnavailableView {
                    Label {
                        Text("machines.not_found")
                    } icon: {
                        MachineIconImage(machineID: machineID)
                    }
                }
            }
        }
    }
}

private struct MachineDetailContent: View {
    @Environment(RunBuoyStore.self) private var store

    let machine: MachineSnapshot
    @State private var notice: LocalizedStringKey?
    @AppStorage private var machineIconName: String

    init(machine: MachineSnapshot) {
        self.machine = machine
        _machineIconName = AppStorage(
            wrappedValue: MachineIcon.defaultValue.rawValue,
            MachineIcon.key(for: machine.id)
        )
    }

    var body: some View {
        Form {
            Section {
                LabeledContent("machine.name", value: machine.displayName)
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
            } header: {
                Text("machine.identity")
            } footer: {
                Text("machine.name_cli_hint")
            }

            Section("machine.appearance") {
                Picker(selection: $machineIconName) {
                    ForEach(MachineIcon.allCases) { icon in
                        Label {
                            Text(icon.title)
                        } icon: {
                            Image(systemName: icon.rawValue)
                        }
                        .tag(icon.rawValue)
                    }
                } label: {
                    Label {
                        Text("machine.icon")
                    } icon: {
                        MachineIconImage(machineID: machine.id)
                    }
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
        .accessibilityIdentifier("screen.machineDetail")
        .navigationTitle(machine.displayName)
        .navigationBarTitleDisplayMode(.inline)
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

private extension MachineIcon {
    var title: LocalizedStringKey {
        switch self {
        case .desktopcomputer:
            "machine.icon.desktopcomputer"
        case .macProServer:
            "machine.icon.macpro_server"
        case .macbook:
            "machine.icon.macbook"
        case .macMini:
            "machine.icon.macmini"
        case .macStudio:
            "machine.icon.macstudio"
        case .macPro:
            "machine.icon.macpro"
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
