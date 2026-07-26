import SwiftUI
import UIKit

@main
struct RunBuoyApp: App {
    @UIApplicationDelegateAdaptor(RunBuoyAppDelegate.self) private var appDelegate
    @Environment(\.scenePhase) private var scenePhase

    @State private var store: RunBuoyStore
    @State private var router = AppRouter()
    @State private var notificationCoordinator = NotificationCoordinator()
    @State private var activityCoordinator: ActivityTokenCoordinator
    @AppStorage("runbuoy.onboarding-complete") private var onboardingComplete = false

    init() {
        let identityStore = KeychainDeviceIdentityStore()
        let api = URLSessionRunBuoyAPI(
            baseURL: AppConfiguration.live.apiBaseURL,
            identityStore: identityStore
        )
        _store = State(
            initialValue: RunBuoyStore(
                api: api,
                identityStore: identityStore,
                cache: LocalCacheStore()
            )
        )
        _activityCoordinator = State(initialValue: ActivityTokenCoordinator(api: api))
    }

    var body: some Scene {
        WindowGroup {
            Group {
                if onboardingComplete {
                    AppShellView()
                } else {
                    OnboardingView(
                        notificationCoordinator: notificationCoordinator,
                        onFinished: { onboardingComplete = true }
                    )
                }
            }
            .environment(store)
            .environment(router)
            .onOpenURL { _ = router.handle($0) }
            .task {
                notificationCoordinator.onRefreshRequested = {
                    Task { await store.refresh() }
                }
                notificationCoordinator.onDeviceToken = { token in
                    Task { try? await registerNotificationToken(token) }
                }
                notificationCoordinator.configure()
                appDelegate.installTokenHandler { data in
                    Task { @MainActor in notificationCoordinator.receive(deviceToken: data) }
                }
                await store.restoreCache()
                if onboardingComplete {
                    UIApplication.shared.registerForRemoteNotifications()
                    activityCoordinator.start()
                    await store.refresh()
                }
            }
            .onChange(of: onboardingComplete) { _, completed in
                if completed {
                    activityCoordinator.start()
                    Task { await store.refresh() }
                }
            }
            .onChange(of: scenePhase) { _, phase in
                guard phase == .active, onboardingComplete else { return }
                activityCoordinator.reconcileCurrentActivities()
                Task { await store.refresh() }
            }
        }
    }

    private func registerNotificationToken(_ token: String) async throws {
        let identityStore = KeychainDeviceIdentityStore()
        let api = URLSessionRunBuoyAPI(
            baseURL: AppConfiguration.live.apiBaseURL,
            identityStore: identityStore
        )
        try await api.registerNotificationToken(token)
    }
}
