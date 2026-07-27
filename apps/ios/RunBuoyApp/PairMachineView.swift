import SwiftUI

enum PairingSheet: String, Identifiable {
    case scanner

    var id: String { rawValue }
}

struct PairMachineView: View {
    @Environment(RunBuoyStore.self) private var store
    @State private var sheet: PairingSheet?
    @State private var code: PairingCode?
    @State private var status: LocalizedStringKey?

    var body: some View {
        Form {
            Section {
                Label("pairing.read_only_note", systemImage: "hand.raised")
            }
            if let code {
                Section("pairing.machine") {
                    LabeledContent("pairing.name", value: code.machineDisplayName)
                    if let platform = code.platform {
                        LabeledContent("machine.platform", value: platform)
                    }
                    Button("pairing.claim", action: claimPairing)
                        .buttonStyle(.glassProminent)
                }
            } else {
                Button(action: showScanner) {
                    Label("pairing.scan_title", systemImage: "qrcode.viewfinder")
                }
                .buttonStyle(.glass)
            }
            if let status {
                Section {
                    Label(status, systemImage: "info.circle")
                }
            }
        }
        .navigationTitle("settings.pair_machine")
        .sheet(item: $sheet) { _ in
            ScannerSheet(onCode: receiveScannedCode)
        }
    }

    private func showScanner() {
        sheet = .scanner
    }

    private func receiveScannedCode(_ value: String) {
        code = try? PairingCode.decode(value)
    }

    private func claimPairing() {
        guard let code else { return }
        Task {
            do {
                try await store.claim(code)
                status = "pairing.success"
            } catch {
                status = "pairing.failed"
            }
        }
    }
}

#Preview {
    NavigationStack {
        PairMachineView()
    }
    .environment(PreviewFixtures.store())
}
