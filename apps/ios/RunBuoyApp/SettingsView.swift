import ActivityKit
import SwiftUI

struct SettingsView: View {
    @Environment(RunBuoyStore.self) private var store
    @AppStorage(AppConfiguration.serverAddressDefaultsKey) private var serverAddress = ""
    @AppStorage("runbuoy.notifications-enabled") private var notificationsEnabled = true
    @AppStorage("runbuoy.live-activities-enabled") private var liveActivitiesEnabled = true
    @AppStorage("runbuoy.safe-messages-enabled") private var safeMessagesEnabled = true
    @State private var cacheMessage: LocalizedStringKey?
    @State private var draftServerAddress = UserDefaults.standard.string(
        forKey: AppConfiguration.serverAddressDefaultsKey
    ) ?? ""
    @State private var serverMessage: LocalizedStringKey?
    @State private var serverValidationAttempted = false
    @FocusState private var isServerFieldFocused: Bool

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
                    TextField(
                        "",
                        text: $draftServerAddress
                    )
                    .multilineTextAlignment(.trailing)
                    .keyboardType(.URL)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .submitLabel(.done)
                    .focused($isServerFieldFocused)
                    .accessibilityLabel("settings.server")
                    .onSubmit(saveServer)
                } label: {
                    Label("settings.server", systemImage: "server.rack")
                }

                if serverValidationAttempted, !isServerValid {
                    Label("settings.server_invalid", systemImage: "exclamationmark.triangle")
                        .font(.footnote)
                        .foregroundStyle(.red)
                } else if let serverMessage {
                    Label(serverMessage, systemImage: "checkmark.circle")
                        .font(.footnote)
                        .foregroundStyle(.primary)
                }
            } header: {
                Text("settings.connections")
            } footer: {
                Text(
                    String(
                        format: String(localized: "settings.server_default"),
                        AppConfiguration.defaultServerAddress
                    )
                )
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
                Link(destination: RunBuoyLinks.privateDeployment) {
                    Label("settings.private_deployment", systemImage: "server.rack")
                        .foregroundStyle(.primary)
                }
                .tint(.primary)
            }
        }
        .scrollEdgeEffectStyle(.hard, for: .bottom)
        .accessibilityIdentifier("screen.settings")
        .navigationTitle("settings.title")
        .onChange(of: notificationsEnabled) { _, _ in savePreferences() }
        .onChange(of: liveActivitiesEnabled) { _, _ in savePreferences() }
        .onChange(of: safeMessagesEnabled) { _, _ in savePreferences() }
        .onChange(of: draftServerAddress) { _, _ in
            serverValidationAttempted = false
            if hasServerChanges {
                serverMessage = nil
            }
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

    private var trimmedServerAddress: String {
        draftServerAddress.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private var resolvedServerURL: URL? {
        AppConfiguration.resolvedAPIBaseURL(
            serverAddress: trimmedServerAddress,
            defaultBaseURL: AppConfiguration.bundledAPIBaseURL
        )
    }

    private var isServerValid: Bool {
        resolvedServerURL != nil
    }

    private var hasServerChanges: Bool {
        trimmedServerAddress != serverAddress
    }

    private func saveServer() {
        serverValidationAttempted = true
        guard isServerValid else {
            serverMessage = nil
            return
        }
        serverValidationAttempted = false
        isServerFieldFocused = false
        guard hasServerChanges else { return }
        serverAddress = trimmedServerAddress
        draftServerAddress = trimmedServerAddress
        serverMessage = "settings.server_saved"
        Task { await store.refresh() }
    }
}

enum RunBuoyLinks {
    static let website = URL(string: "https://www.runbuoy.cloud")!
    static let privacy = URL(string: "https://www.runbuoy.cloud/privacy")!
    static let privateDeployment = URL(string: "https://www.runbuoy.cloud/self-hosting")!
}

#Preview {
    NavigationStack { SettingsView() }
        .environment(PreviewFixtures.store())
        .environment(AppRouter())
}
