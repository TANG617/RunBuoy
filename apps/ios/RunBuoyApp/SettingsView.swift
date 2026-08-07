import ActivityKit
import LocalAuthentication
import SwiftUI

struct SettingsView: View {
    @Environment(RunBuoyStore.self) private var store
    @AppStorage("runbuoy.onboarding-complete") private var onboardingComplete = false
    @AppStorage("runbuoy.notifications-enabled") private var notificationsEnabled = true
    @AppStorage("runbuoy.live-activities-enabled") private var liveActivitiesEnabled = true
    @AppStorage("runbuoy.safe-messages-enabled") private var safeMessagesEnabled = true
    @State private var cacheMessage: LocalizedStringKey?
    @State private var confirmsDeviceReset = false
    @State private var confirmsLocalReset = false
    @State private var confirmsWorkspaceDeletion = false
    @State private var isPerformingDestructiveAction = false
    @State private var lifecycleNotice: String?
    private let ownerAuthorizer: any DeviceOwnerAuthorizing

    init(ownerAuthorizer: any DeviceOwnerAuthorizing = LocalDeviceOwnerAuthorizer()) {
        self.ownerAuthorizer = ownerAuthorizer
    }

    var body: some View {
        Form {
            Section {
                NavigationLink(value: AppRoute.machines) {
                    LabeledContent {
                        Text(store.machines.count, format: .number)
                            .foregroundStyle(.primary)
                    } label: {
                        Label("settings.machines", systemImage: "desktopcomputer.and.macbook")
                    }
                }
                .accessibilityIdentifier("settings.machines")

                LabeledContent {
                    Text(selectedRegionName)
                        .foregroundStyle(.secondary)
                } label: {
                    Label("settings.region", systemImage: "globe.asia.australia")
                }

                LabeledContent {
                    Text(AppConfiguration.displayAddress(for: AppConfiguration.live.apiBaseURL))
                        .foregroundStyle(.secondary)
                } label: {
                    Label("settings.server", systemImage: "server.rack")
                }
            } header: {
                Text("settings.connections")
            } footer: {
                Text("settings.region_locked")
            }

            Section {
                NavigationLink(value: AppRoute.capabilityDemo) {
                    Label("demo.settings_entry", systemImage: "sparkles")
                }
                .accessibilityIdentifier("settings.capabilityDemo")
            } header: {
                Text("settings.product")
            } footer: {
                Text("demo.settings_footer")
            }

            Section("settings.notifications") {
                Toggle("settings.notifications_enabled", isOn: $notificationsEnabled)
                    .accessibilityIdentifier("settings.notifications")
                Toggle("settings.live_activities", isOn: $liveActivitiesEnabled)
                    .disabled(!ActivityAuthorizationInfo().areActivitiesEnabled)
                    .accessibilityIdentifier("settings.liveActivities")
                Toggle("settings.safe_messages", isOn: $safeMessagesEnabled)
                    .accessibilityIdentifier("settings.safeMessages")
                if !ActivityAuthorizationInfo().areActivitiesEnabled {
                    Label("settings.live_activities_system_disabled", systemImage: "exclamationmark.triangle")
                        .font(.footnote)
                        .foregroundStyle(.primary)
                }
            }

            Section("settings.storage") {
                Button(action: clearCache) {
                    Label("settings.clear_cache", systemImage: "trash")
                        .foregroundStyle(.primary)
                }
                .tint(.primary)
                .accessibilityIdentifier("settings.clearCache")
                if let cacheMessage {
                    Text(cacheMessage)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .accessibilityIdentifier("settings.cacheCleared")
                }
            }

            Section {
                Button(role: .destructive) {
                    confirmsDeviceReset = true
                } label: {
                    Label("settings.reset_device", systemImage: "iphone.slash")
                }
                .disabled(isPerformingDestructiveAction || store.deviceIdentity == nil)
                .accessibilityIdentifier("settings.resetDevice")

                Button(role: .destructive) {
                    confirmsLocalReset = true
                } label: {
                    Label("settings.reset_local_only", systemImage: "externaldrive.badge.xmark")
                }
                .disabled(isPerformingDestructiveAction)
                .accessibilityIdentifier("settings.resetLocalOnly")

                Button(role: .destructive) {
                    confirmsWorkspaceDeletion = true
                } label: {
                    Label("settings.delete_workspace", systemImage: "trash.slash")
                }
                .disabled(isPerformingDestructiveAction || store.deviceIdentity == nil)
                .accessibilityIdentifier("settings.deleteWorkspace")

                if isPerformingDestructiveAction {
                    HStack {
                        ProgressView()
                        Text("settings.lifecycle_working")
                    }
                    .accessibilityIdentifier("settings.lifecycleWorking")
                }
                if let lifecycleNotice {
                    Text(lifecycleNotice)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .accessibilityIdentifier("settings.lifecycleNotice")
                }
            } header: {
                Text("settings.identity_data")
            } footer: {
                Text("settings.identity_data_explanation")
            }

            Section("settings.about") {
                Link(destination: RunBuoyLinks.website) {
                    Label("settings.website", systemImage: "globe")
                        .foregroundStyle(.primary)
                }
                .tint(.primary)
                Link(destination: RunBuoyLinks.privacy) {
                    Label("settings.privacy", systemImage: "hand.raised")
                        .foregroundStyle(.primary)
                }
                .tint(.primary)
                Link(destination: RunBuoyLinks.support) {
                    Label("settings.support", systemImage: "questionmark.circle")
                        .foregroundStyle(.primary)
                }
                .tint(.primary)
                Link(destination: RunBuoyLinks.privateDeployment) {
                    Label("settings.private_deployment", systemImage: "server.rack")
                        .foregroundStyle(.primary)
                }
                .tint(.primary)
            }
        }
        .runBuoyBottomScrollEdgeStyle()
        .accessibilityIdentifier("screen.settings")
        .navigationTitle("settings.title")
        .onChange(of: notificationsEnabled) { _, _ in savePreferences() }
        .onChange(of: liveActivitiesEnabled) { _, _ in savePreferences() }
        .onChange(of: safeMessagesEnabled) { _, _ in savePreferences() }
        .confirmationDialog(
            "settings.reset_device_confirm_title",
            isPresented: $confirmsDeviceReset,
            titleVisibility: .visible
        ) {
            Button("settings.reset_device_confirm", role: .destructive) {
                performLifecycleAction(.resetDevice)
            }
            Button("common.cancel", role: .cancel) {}
        } message: {
            Text("settings.reset_device_confirm_message")
        }
        .confirmationDialog(
            "settings.reset_local_confirm_title",
            isPresented: $confirmsLocalReset,
            titleVisibility: .visible
        ) {
            Button("settings.reset_local_confirm", role: .destructive) {
                performLifecycleAction(.resetLocalOnly)
            }
            Button("common.cancel", role: .cancel) {}
        } message: {
            Text("settings.reset_local_confirm_message")
        }
        .confirmationDialog(
            "settings.delete_workspace_confirm_title",
            isPresented: $confirmsWorkspaceDeletion,
            titleVisibility: .visible
        ) {
            Button("settings.delete_workspace_confirm", role: .destructive) {
                performLifecycleAction(.deleteWorkspace)
            }
            Button("common.cancel", role: .cancel) {}
        } message: {
            Text("settings.delete_workspace_confirm_message")
        }
    }

    private func savePreferences() {
        let preferences = DevicePreferences(
            notificationsEnabled: notificationsEnabled,
            liveActivitiesEnabled: liveActivitiesEnabled,
            showSafeMessages: safeMessagesEnabled
        )
        Task { await store.savePreferences(preferences) }
    }

    private func clearCache() {
        Task {
            try? await store.clearCache()
            cacheMessage = "settings.cache_cleared"
        }
    }

    private func performLifecycleAction(_ action: SettingsLifecycleAction) {
        guard !isPerformingDestructiveAction else { return }
        isPerformingDestructiveAction = true
        lifecycleNotice = nil
        Task { @MainActor in
            let authorized = await ownerAuthorizer.authorize(reason: action.authorizationReason)
            guard authorized else {
                lifecycleNotice = String(localized: "settings.lifecycle_auth_cancelled")
                isPerformingDestructiveAction = false
                return
            }
            do {
                switch action {
                case .resetDevice:
                    try await store.resetDevice()
                case .resetLocalOnly:
                    try await store.resetDeviceLocalOnly()
                case .deleteWorkspace:
                    try await store.deleteWorkspace()
                }
                onboardingComplete = false
                lifecycleNotice = String(localized: action.successKey)
            } catch {
                lifecycleNotice = String(
                    format: String(localized: "settings.lifecycle_failed"),
                    error.localizedDescription
                )
            }
            isPerformingDestructiveAction = false
        }
    }

    private var selectedRegionName: String {
        AppConfiguration.selectedRegion()?.displayName
            ?? String(localized: "region.private_deployment")
    }
}

protocol DeviceOwnerAuthorizing: Sendable {
    func authorize(reason: String) async -> Bool
}

struct LocalDeviceOwnerAuthorizer: DeviceOwnerAuthorizing {
    func authorize(reason: String) async -> Bool {
        let context = LAContext()
        var evaluationError: NSError?
        guard context.canEvaluatePolicy(.deviceOwnerAuthentication, error: &evaluationError) else {
            // The explicit destructive confirmation remains the fallback on a
            // device that has no owner-authentication policy configured.
            return true
        }
        do {
            return try await context.evaluatePolicy(
                .deviceOwnerAuthentication,
                localizedReason: reason
            )
        } catch {
            return false
        }
    }
}

private enum SettingsLifecycleAction {
    case resetDevice
    case resetLocalOnly
    case deleteWorkspace

    var authorizationReason: String {
        switch self {
        case .resetDevice:
            String(localized: "settings.reset_device_auth_reason")
        case .resetLocalOnly:
            String(localized: "settings.reset_local_auth_reason")
        case .deleteWorkspace:
            String(localized: "settings.delete_workspace_auth_reason")
        }
    }

    var successKey: String.LocalizationValue {
        switch self {
        case .resetDevice:
            "settings.reset_device_succeeded"
        case .resetLocalOnly:
            "settings.reset_local_succeeded"
        case .deleteWorkspace:
            "settings.delete_workspace_succeeded"
        }
    }
}

enum RunBuoyLinks {
    static let website = URL(string: "https://www.runbuoy.cloud")!
    static let privacy = URL(string: "https://www.runbuoy.cloud/privacy")!
    static let support = URL(string: "https://www.runbuoy.cloud/support")!
    static let privateDeployment = URL(string: "https://www.runbuoy.cloud/self-hosting")!
}

#Preview {
    NavigationStack { SettingsView() }
        .environment(PreviewFixtures.store())
        .environment(AppRouter())
}
