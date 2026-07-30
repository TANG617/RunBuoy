import SwiftUI
import UIKit

private enum OnboardingSheet: String, Identifiable {
    case scanner
    case pairingCode

    var id: String { rawValue }
}

struct OnboardingView: View {
    @Environment(RunBuoyStore.self) private var store
    @Environment(AppRouter.self) private var router
    let notificationCoordinator: NotificationCoordinator
    let bypassesSystemPermissions: Bool
    let onFinished: () -> Void

    @State private var page = 0
    @State private var sheet: OnboardingSheet?
    @State private var pairingCode: PairingCode?
    @State private var pairingSucceeded = false
    @State private var errorMessage: String?
    @State private var isWorking = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    init(
        notificationCoordinator: NotificationCoordinator,
        bypassesSystemPermissions: Bool = false,
        onFinished: @escaping () -> Void
    ) {
        self.notificationCoordinator = notificationCoordinator
        self.bypassesSystemPermissions = bypassesSystemPermissions
        self.onFinished = onFinished
    }

    var body: some View {
        VStack(spacing: 24) {
            TabView(selection: $page) {
                ProductIntroduction()
                    .tag(0)
                PermissionIntroduction()
                    .tag(1)
                PairingIntroduction()
                    .tag(2)
            }
            .tabViewStyle(.page(indexDisplayMode: .always))
            .animation(reduceMotion ? nil : .default, value: page)

            if page == 2, let pairingCode {
                PairingIdentityCard(code: pairingCode)
            }
            if pairingSucceeded {
                Label("pairing.success", systemImage: "checkmark.circle.fill")
                    .font(.headline)
                    .foregroundStyle(.green)
                    .accessibilityIdentifier("onboarding.pairing-success")
            }
            if let errorMessage {
                Label(errorMessage, systemImage: "exclamationmark.triangle")
                    .font(.footnote)
                    .foregroundStyle(.red)
                    .padding(.horizontal)
            }

            VStack(spacing: 12) {
                Button(action: advanceAction) {
                    if isWorking {
                        ProgressView()
                            .frame(maxWidth: .infinity)
                    } else {
                        Label(primaryTitle, systemImage: primarySymbol)
                            .frame(maxWidth: .infinity)
                    }
                }
                .buttonStyle(.glassProminent)
                .controlSize(.large)
                .disabled(isWorking)
                .accessibilityIdentifier("onboarding.primary-action")

                if page == 2, pairingCode == nil, !pairingSucceeded {
                    Button {
                        sheet = .pairingCode
                    } label: {
                        Label("pairing.enter_code", systemImage: "keyboard")
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.glass)
                    .controlSize(.large)
                    .disabled(isWorking)
                    .accessibilityIdentifier("onboarding.enter-code")
                }
            }
            .padding()
        }
        .background(Color(uiColor: .systemGroupedBackground))
        .sheet(item: $sheet) { presentedSheet in
            switch presentedSheet {
            case .scanner:
                ScannerSheet(onCode: receiveScannedCode)
            case .pairingCode:
                PairingCodeEntrySheet(code: $pairingCode)
            }
        }
        .onAppear {
            receivePendingPairingCode(router.pendingPairingCode)
        }
        .onChange(of: router.pendingPairingCode) { _, code in
            receivePendingPairingCode(code)
        }
    }

    private var primaryTitle: LocalizedStringKey {
        switch page {
        case 0: "onboarding.continue"
        case 1: "onboarding.enable_notifications"
        default:
            if pairingSucceeded {
                "onboarding.finish"
            } else {
                pairingCode == nil ? "onboarding.scan_code" : "onboarding.confirm_machine"
            }
        }
    }

    private var primarySymbol: String {
        switch page {
        case 0: "arrow.right"
        case 1: "bell.badge"
        default: pairingSucceeded ? "checkmark" : (pairingCode == nil ? "qrcode.viewfinder" : "checkmark.shield")
        }
    }

    private func advanceAction() {
        Task { await advance() }
    }

    private func receiveScannedCode(_ value: String) {
        do {
            pairingCode = try PairingCode.decode(value)
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func advance() async {
        errorMessage = nil
        switch page {
        case 0:
            page = 1
        case 1:
            isWorking = true
            do {
                if bypassesSystemPermissions {
                    _ = try await store.bootstrapDevice()
                } else {
                    _ = try await notificationCoordinator.requestAuthorization()
                    _ = try await store.bootstrapDevice()
                    UIApplication.shared.registerForRemoteNotifications()
                }
                page = 2
            } catch {
                errorMessage = error.localizedDescription
            }
            isWorking = false
        default:
            if pairingSucceeded {
                router.clearPendingPairing()
                router.selectedTab = .activeRuns
                onFinished()
                return
            }
            guard let pairingCode else {
                sheet = .scanner
                return
            }
            isWorking = true
            do {
                try await store.claim(pairingCode)
                pairingSucceeded = true
            } catch {
                errorMessage = error.localizedDescription
            }
            isWorking = false
        }
    }

    private func receivePendingPairingCode(_ code: PairingCode?) {
        guard let code else { return }
        pairingCode = code
        errorMessage = nil
    }
}

private struct ProductIntroduction: View {
    var body: some View {
        OnboardingPage(
            symbol: "water.waves",
            title: "onboarding.welcome",
            bodyText: "onboarding.welcome_body"
        ) {
            VStack(alignment: .leading, spacing: 15) {
                BoundaryRow(symbol: "arrow.right.circle", title: "onboarding.flow_machine")
                BoundaryRow(symbol: "server.rack", title: "onboarding.flow_server")
                BoundaryRow(symbol: "iphone", title: "onboarding.flow_phone")
            }
        }
        .accessibilityIdentifier("onboarding.page.product")
    }
}

private struct PermissionIntroduction: View {
    var body: some View {
        OnboardingPage(
            symbol: "bell.badge.fill",
            title: "onboarding.notifications",
            bodyText: "onboarding.notifications_body"
        ) {
            VStack(alignment: .leading, spacing: 14) {
                BoundaryRow(symbol: "waveform.path.ecg", title: "onboarding.live_updates")
                BoundaryRow(symbol: "lock.fill", title: "onboarding.tokens_private")
            }
        }
        .accessibilityIdentifier("onboarding.page.permissions")
    }
}

private struct PairingIntroduction: View {
    var body: some View {
        OnboardingPage(
            symbol: "qrcode.viewfinder",
            title: "onboarding.pair",
            bodyText: "onboarding.pair_body"
        ) {
            Label("onboarding.one_time_code", systemImage: "clock.badge.checkmark")
                .font(.headline)
        }
        .accessibilityIdentifier("onboarding.page.pairing")
    }
}

private struct OnboardingPage<Content: View>: View {
    let symbol: String
    let title: LocalizedStringKey
    let bodyText: LocalizedStringKey
    let content: Content

    init(
        symbol: String,
        title: LocalizedStringKey,
        bodyText: LocalizedStringKey,
        @ViewBuilder content: () -> Content
    ) {
        self.symbol = symbol
        self.title = title
        self.bodyText = bodyText
        self.content = content()
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 22) {
                Image(systemName: symbol)
                    .font(.system(size: 58, weight: .semibold))
                    .foregroundStyle(.tint)
                    .accessibilityHidden(true)
                Text(title)
                    .font(.largeTitle.bold())
                    .multilineTextAlignment(.center)
                Text(bodyText)
                    .font(.title3)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                content
                    .frame(maxWidth: 420, alignment: .leading)
            }
            .padding(28)
        }
    }
}

private struct BoundaryRow: View {
    let symbol: String
    let title: LocalizedStringKey

    var body: some View {
        Label(title, systemImage: symbol)
            .font(.headline)
            .accessibilityElement(children: .combine)
    }
}

private struct PairingIdentityCard: View {
    let code: PairingCode

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("pairing.confirm_identity", systemImage: "checkmark.shield")
                .font(.headline)
            Text(code.machineDisplayName)
                .font(.title3.bold())
            if let platform = code.platform {
                Text(platform)
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.background, in: RoundedRectangle(cornerRadius: 16))
        .padding(.horizontal)
        .accessibilityIdentifier("onboarding.pairing-identity")
    }
}

#Preview("English") {
    OnboardingView(notificationCoordinator: NotificationCoordinator(), onFinished: {})
        .environment(PreviewFixtures.store())
        .environment(AppRouter())
}

#Preview("简体中文 · 大字体") {
    OnboardingView(notificationCoordinator: NotificationCoordinator(), onFinished: {})
        .environment(PreviewFixtures.store())
        .environment(AppRouter())
        .environment(\.locale, Locale(identifier: "zh-Hans"))
        .environment(\.dynamicTypeSize, .accessibility3)
}
