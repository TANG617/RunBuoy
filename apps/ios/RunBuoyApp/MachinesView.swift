import SwiftUI

struct MachinesView: View {
    @Environment(RunBuoyStore.self) private var store

    var body: some View {
        Group {
            if store.machines.isEmpty {
                ContentUnavailableView {
                    Label("machines.empty", systemImage: "desktopcomputer")
                } description: {
                    Text("machines.empty_description")
                }
            } else {
                List(store.machines) { machine in
                    NavigationLink(value: AppRoute.machine(machine.id)) {
                        MachineRow(machine: machine)
                    }
                }
                .listStyle(.insetGrouped)
                .refreshable { await store.refresh() }
            }
        }
        .navigationTitle("machines.title")
    }
}

struct MachineRow: View {
    let machine: MachineSnapshot

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: machine.isSubscribed ? "desktopcomputer" : "desktopcomputer.trianglebadge.exclamationmark")
                .font(.title2)
                .foregroundStyle(
                    machine.isSubscribed
                        ? Color.accentColor
                        : Color(uiColor: .secondaryLabel)
                )
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

    private var localLabel: String {
        UserDefaults.standard.string(forKey: "runbuoy.machine-label.\(machine.id)") ?? machine.displayName
    }
}

struct MachineDetailView: View {
    let machineID: String
    @Environment(RunBuoyStore.self) private var store
    @State private var localLabel = ""
    @State private var notice: LocalizedStringKey?

    var body: some View {
        if let machine = store.machines.first(where: { $0.id == machineID }) {
            Form {
                Section("machine.identity") {
                    TextField("machine.local_label", text: $localLabel)
                        .textInputAutocapitalization(.words)
                        .accessibilityHint("machine.local_label_hint")
                    Button("machine.save_local_label") {
                        let value = localLabel.trimmingCharacters(in: .whitespacesAndNewlines)
                        if value.isEmpty {
                            UserDefaults.standard.removeObject(forKey: labelKey)
                        } else {
                            UserDefaults.standard.set(value, forKey: labelKey)
                        }
                        notice = "machine.label_saved"
                    }
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
                    if machine.isSubscribed, let subscriptionID = machine.subscriptionID {
                        Button("machine.stop_receiving", role: .destructive) {
                            Task {
                                try? await store.stopReceiving(subscriptionID: subscriptionID)
                                notice = "machine.receiving_stopped"
                            }
                        }
                    }
                    Button("machine.remove_pairing", role: .destructive) {
                        Task {
                            try? await store.removeLocalPairing(subscriptionID: machine.subscriptionID)
                            notice = "machine.pairing_removed"
                        }
                    }
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
            .onAppear {
                localLabel = UserDefaults.standard.string(forKey: labelKey) ?? machine.displayName
            }
        } else {
            ContentUnavailableView("machines.not_found", systemImage: "desktopcomputer")
        }
    }

    private var labelKey: String {
        "runbuoy.machine-label.\(machineID)"
    }
}

#Preview {
    NavigationStack { MachinesView() }
        .environment(PreviewFixtures.store())
}
