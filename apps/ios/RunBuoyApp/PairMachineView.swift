import SwiftUI

private enum PairingStatus: Equatable {
    case success
    case invalidCode
    case failed

    var title: LocalizedStringKey {
        switch self {
        case .success:
            "pairing.success"
        case .invalidCode:
            "pairing.invalid_code"
        case .failed:
            "pairing.failed"
        }
    }

    var symbol: String {
        self == .success ? "checkmark.circle" : "exclamationmark.triangle"
    }

    var color: Color {
        self == .success ? .green : .red
    }
}

struct PairMachineView: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(RunBuoyStore.self) private var store
    @Environment(AppRouter.self) private var router

    let allowsCodeEntry: Bool
    let dismissesOnSuccess: Bool

    @State private var code: PairingCode?
    @State private var rawCode = ""
    @State private var status: PairingStatus?
    @State private var isWorking = false
    @FocusState private var isCodeFieldFocused: Bool

    init(
        initialCode: PairingCode? = nil,
        allowsCodeEntry: Bool = true,
        dismissesOnSuccess: Bool = false
    ) {
        self.allowsCodeEntry = allowsCodeEntry
        self.dismissesOnSuccess = dismissesOnSuccess
        _code = State(initialValue: initialCode)
    }

    var body: some View {
        Form {
            if let code {
                Section("pairing.machine") {
                    LabeledContent("pairing.name", value: code.machineDisplayName)
                        .accessibilityIdentifier("pairing.machineName")
                    if let platform = code.platform {
                        LabeledContent("machine.platform", value: platform)
                    }
                    Button(action: claimPairing) {
                        if isWorking {
                            ProgressView()
                                .frame(maxWidth: .infinity)
                        } else {
                            Text("pairing.claim")
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .buttonStyle(.glassProminent)
                    .disabled(isWorking)
                    .accessibilityIdentifier("pairing.claim")
                }
            } else if allowsCodeEntry {
                Section {
                    TextField(
                        "pairing.code_placeholder",
                        text: $rawCode,
                        axis: .vertical
                    )
                    .lineLimit(3...6)
                    .keyboardType(.asciiCapable)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .submitLabel(.done)
                    .focused($isCodeFieldFocused)
                    .onSubmit(validateCode)
                    .accessibilityIdentifier("pairing.code")

                    Button("pairing.continue", action: validateCode)
                        .disabled(trimmedCode.isEmpty)
                        .accessibilityIdentifier("pairing.continue")
                } header: {
                    Text("pairing.enter_code")
                } footer: {
                    Text("pairing.code_hint")
                }
            } else {
                ContentUnavailableView(
                    "pairing.invalid_code_title",
                    systemImage: "exclamationmark.triangle"
                )
            }

            if let status {
                Section {
                    Label(status.title, systemImage: status.symbol)
                        .foregroundStyle(status.color)
                        .accessibilityIdentifier("pairing.status")
                }
            }
        }
        .accessibilityIdentifier("screen.pairMachine")
        .navigationTitle(code == nil ? "pairing.enter_code" : "settings.pair_machine")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear {
            receivePendingPairingCode(router.pendingPairingCode)
            if code == nil, allowsCodeEntry {
                isCodeFieldFocused = true
            }
        }
        .onChange(of: router.pendingPairingCode) { _, pendingCode in
            receivePendingPairingCode(pendingCode)
        }
    }

    private var trimmedCode: String {
        rawCode.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func validateCode() {
        do {
            let decoded = try PairingCode.decode(trimmedCode)
            try decoded.requireSelectedRegion()
            code = decoded
            status = nil
            isCodeFieldFocused = false
        } catch {
            status = .invalidCode
        }
    }

    private func receivePendingPairingCode(_ pendingCode: PairingCode?) {
        guard let pendingCode else { return }
        do {
            try pendingCode.requireSelectedRegion()
            code = pendingCode
            status = nil
            isCodeFieldFocused = false
        } catch {
            code = nil
            status = .invalidCode
        }
    }

    private func claimPairing() {
        guard let code, !isWorking else { return }
        isWorking = true
        Task {
            do {
                try await store.claim(code)
                status = .success
                if dismissesOnSuccess {
                    router.pendingPairingCode = nil
                    dismiss()
                } else {
                    router.clearPendingPairing()
                }
            } catch {
                status = .failed
            }
            isWorking = false
        }
    }
}

#Preview("Enter Pairing Code") {
    NavigationStack {
        PairMachineView()
    }
    .environment(PreviewFixtures.store())
    .environment(AppRouter())
}

#Preview("Confirm Pairing") {
    NavigationStack {
        PairMachineView(
            initialCode: PairingCode(
                sessionID: "session_preview",
                challenge: "preview",
                machineDisplayName: "Mac Studio",
                platform: "macOS"
            )
        )
    }
    .environment(PreviewFixtures.store())
    .environment(AppRouter())
}
