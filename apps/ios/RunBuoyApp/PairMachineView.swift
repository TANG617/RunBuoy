import SwiftUI

private enum PairingStatus: Equatable {
    case success
    case failed

    var title: LocalizedStringKey {
        switch self {
        case .success:
            "pairing.success"
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
    @State private var status: PairingStatus?
    @State private var isWorking = false

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
                PairingCodeEntrySection(code: $code)
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
        }
        .onChange(of: router.pendingPairingCode) { _, pendingCode in
            receivePendingPairingCode(pendingCode)
        }
    }

    private func receivePendingPairingCode(_ pendingCode: PairingCode?) {
        guard let pendingCode else { return }
        code = pendingCode
        status = nil
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

struct PairingCodeEntrySheet: View {
    @Environment(\.dismiss) private var dismiss
    @Binding var code: PairingCode?

    var body: some View {
        NavigationStack {
            Form {
                PairingCodeEntrySection(code: $code, dismissesOnResolve: true)
            }
            .navigationTitle("pairing.enter_code")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("common.close") {
                        dismiss()
                    }
                }
            }
        }
        .presentationDetents([.medium])
    }
}

private struct PairingCodeEntrySection: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(RunBuoyStore.self) private var store
    @Binding var code: PairingCode?
    let dismissesOnResolve: Bool

    @State private var rawCode = ""
    @State private var errorMessage: String?
    @State private var isWorking = false
    @FocusState private var isCodeFieldFocused: Bool

    init(
        code: Binding<PairingCode?>,
        dismissesOnResolve: Bool = false
    ) {
        _code = code
        self.dismissesOnResolve = dismissesOnResolve
    }

    var body: some View {
        Section {
            TextField("pairing.short_code_placeholder", text: $rawCode)
                .keyboardType(.numberPad)
                .textContentType(.oneTimeCode)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .font(.title3.monospacedDigit())
                .multilineTextAlignment(.center)
                .focused($isCodeFieldFocused)
                .onSubmit(resolveCode)
                .accessibilityIdentifier("pairing.code")

            Button(action: resolveCode) {
                if isWorking {
                    ProgressView()
                        .frame(maxWidth: .infinity)
                } else {
                    Text("pairing.continue")
                        .frame(maxWidth: .infinity)
                }
            }
            .disabled(trimmedCode.isEmpty || isWorking)
            .accessibilityIdentifier("pairing.continue")

            if let errorMessage {
                Label(errorMessage, systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.red)
                    .accessibilityIdentifier("pairing.status")
            }
        } header: {
            Text("pairing.enter_code")
        } footer: {
            Text("pairing.code_hint")
        }
        .onAppear {
            isCodeFieldFocused = true
        }
    }

    private var trimmedCode: String {
        rawCode.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func resolveCode() {
        guard !trimmedCode.isEmpty, !isWorking else { return }
        isWorking = true
        errorMessage = nil
        Task {
            do {
                let resolvedCode: PairingCode
                if let encodedCode = try? PairingCode.decode(trimmedCode) {
                    resolvedCode = encodedCode
                } else {
                    guard trimmedCode.count == 6,
                          trimmedCode.allSatisfy(\.isNumber)
                    else {
                        throw PairingCodeError.invalidCode
                    }
                    resolvedCode = try await store.resolvePairingCode(trimmedCode)
                }
                code = resolvedCode
                isCodeFieldFocused = false
                if dismissesOnResolve {
                    dismiss()
                }
            } catch APIError.httpStatus(404) {
                errorMessage = String(localized: "pairing.code_invalid_or_expired")
            } catch APIError.httpStatus(429) {
                errorMessage = String(localized: "pairing.too_many_attempts")
            } catch {
                errorMessage = error.localizedDescription
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
