import SwiftUI

enum PairingSheet: String, Identifiable {
    case scanner

    var id: String { rawValue }
}

struct PairMachineView: View {
    @Environment(RunBuoyStore.self) private var store
    @Environment(AppRouter.self) private var router
    @State private var sheet: PairingSheet?
    @State private var code: PairingCode?
    @State private var status: LocalizedStringKey?

    var body: some View {
        Form {
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
        .onAppear {
            receivePendingPairingCode(router.pendingPairingCode)
        }
        .onChange(of: router.pendingPairingCode) { _, pendingCode in
            receivePendingPairingCode(pendingCode)
        }
    }

    private func showScanner() {
        sheet = .scanner
    }

    private func receiveScannedCode(_ value: String) {
        code = try? PairingCode.decode(value)
    }

    private func receivePendingPairingCode(_ pendingCode: PairingCode?) {
        guard let pendingCode else { return }
        code = pendingCode
    }

    private func claimPairing() {
        guard let code else { return }
        Task {
            do {
                try await store.claim(code)
                router.clearPendingPairing()
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
    .environment(AppRouter())
}
