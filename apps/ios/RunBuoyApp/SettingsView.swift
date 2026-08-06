import ActivityKit
import SwiftUI

struct SettingsView: View {
    @Environment(RunBuoyStore.self) private var store
    @AppStorage("runbuoy.notifications-enabled") private var notificationsEnabled = true
    @AppStorage("runbuoy.live-activities-enabled") private var liveActivitiesEnabled = true
    @AppStorage("runbuoy.safe-messages-enabled") private var safeMessagesEnabled = true
    @State private var cacheMessage: LocalizedStringKey?

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
        .scrollEdgeEffectHidden(true, for: .bottom)
        .accessibilityIdentifier("screen.settings")
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

    private func clearCache() {
        Task {
            try? await store.clearCache()
            cacheMessage = "settings.cache_cleared"
        }
    }

    private var selectedRegionName: String {
        AppConfiguration.selectedRegion()?.displayName
            ?? String(localized: "region.private_deployment")
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
