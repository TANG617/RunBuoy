import ActivityKit
import SwiftUI

struct SettingsView: View {
    @Environment(RunBuoyStore.self) private var store
    @Environment(AppRouter.self) private var router
    @AppStorage("runbuoy.notifications-enabled") private var notificationsEnabled = true
    @AppStorage("runbuoy.live-activities-enabled") private var liveActivitiesEnabled = true
    @AppStorage("runbuoy.safe-messages-enabled") private var safeMessagesEnabled = true
    @State private var cacheMessage: LocalizedStringKey?

    var body: some View {
        Form {
            Section("settings.connections") {
                NavigationLink(value: AppRoute.machines) {
                    LabeledContent {
                        Text(store.machines.count, format: .number)
                    } label: {
                        Label("settings.machines", systemImage: "desktopcomputer")
                    }
                }
                NavigationLink(value: AppRoute.pairMachine) {
                    Label("settings.pair_machine", systemImage: "qrcode.viewfinder")
                }
            }

            Section("settings.notifications") {
                Toggle("settings.notifications_enabled", isOn: $notificationsEnabled)
                Toggle("settings.live_activities", isOn: $liveActivitiesEnabled)
                    .disabled(!ActivityAuthorizationInfo().areActivitiesEnabled)
                Toggle("settings.safe_messages", isOn: $safeMessagesEnabled)
                if !ActivityAuthorizationInfo().areActivitiesEnabled {
                    Label("settings.live_activities_system_disabled", systemImage: "exclamationmark.triangle")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }

            Section("settings.storage") {
                Button {
                    Task {
                        try? await store.clearCache()
                        cacheMessage = "settings.cache_cleared"
                    }
                } label: {
                    Label("settings.clear_cache", systemImage: "trash")
                }
                if let cacheMessage {
                    Text(cacheMessage)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }

            Section("settings.about") {
                LabeledContent("settings.product", value: "RunBuoy")
                LabeledContent("settings.boundary", value: String(localized: "settings.read_only"))
                LabeledContent("settings.server", value: AppConfiguration.live.apiBaseURL.host ?? "—")
                Link(destination: URL(string: "https://runbuoy.dev/privacy")!) {
                    Label("settings.privacy", systemImage: "hand.raised")
                }
            }
        }
        .navigationTitle("settings.title")
        .onChange(of: notificationsEnabled) { _, _ in savePreferences() }
        .onChange(of: liveActivitiesEnabled) { _, _ in savePreferences() }
        .onChange(of: safeMessagesEnabled) { _, _ in savePreferences() }
    }

    private func savePreferences() {
        let preferences = DevicePreferences(
            notificationsEnabled: notificationsEnabled,
            liveActivitiesEnabled: liveActivitiesEnabled,
            showSafeMessages: safeMessagesEnabled
        )
        Task { await store.savePreferences(preferences) }
    }
}

#Preview {
    NavigationStack { SettingsView() }
        .environment(PreviewFixtures.store())
        .environment(AppRouter())
}
