import SwiftUI
import UIKit

@main
struct RunBuoyApp: App {
    @UIApplicationDelegateAdaptor(RunBuoyAppDelegate.self) private var appDelegate
    @Environment(\.scenePhase) private var scenePhase

    @State private var store: RunBuoyStore
    @State private var router: AppRouter
    @State private var notificationCoordinator = NotificationCoordinator()
    @State private var activityCoordinator: ActivityTokenCoordinator
    @AppStorage("runbuoy.onboarding-complete") private var onboardingComplete = false
    private let isUIPreviewMode: Bool

    init() {
        let isUIPreviewMode = Self.isUIPreviewLaunch
        let identityStore = KeychainDeviceIdentityStore()
        let api = URLSessionRunBuoyAPI(
            baseURL: AppConfiguration.live.apiBaseURL,
            identityStore: identityStore
        )
        let router = AppRouter()
        if let previewTab = Self.uiPreviewTab {
            router.selectedTab = previewTab
        }
        if let previewRunID = Self.uiPreviewRunID {
            router.selectedTab = .activeRuns
            router.activeRunsPath = [.runDetail(previewRunID)]
        }
        _router = State(initialValue: router)
        if isUIPreviewMode {
            _store = State(initialValue: PreviewFixtures.store())
        } else {
            _store = State(
                initialValue: RunBuoyStore(
                    api: api,
                    identityStore: identityStore,
                    cache: LocalCacheStore()
                )
            )
        }
        _activityCoordinator = State(initialValue: ActivityTokenCoordinator(api: api))
        self.isUIPreviewMode = isUIPreviewMode
    }

    var body: some Scene {
        WindowGroup {
            Group {
                if onboardingComplete || isUIPreviewMode {
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
                guard !isUIPreviewMode else { return }
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
                if completed, !isUIPreviewMode {
                    activityCoordinator.start()
                    Task { await store.refresh() }
                }
            }
            .onChange(of: scenePhase) { _, phase in
                guard phase == .active, onboardingComplete, !isUIPreviewMode else { return }
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

    private static var isUIPreviewLaunch: Bool {
#if DEBUG
        ProcessInfo.processInfo.arguments.contains("-runbuoy-ui-preview")
#else
        false
#endif
    }

    private static var uiPreviewTab: AppTab? {
#if DEBUG
        let arguments = ProcessInfo.processInfo.arguments
        guard let flagIndex = arguments.firstIndex(of: "-runbuoy-ui-preview-tab"),
              arguments.indices.contains(flagIndex + 1)
        else {
            return nil
        }
        return AppTab(rawValue: arguments[flagIndex + 1])
#else
        nil
#endif
    }

    private static var uiPreviewRunID: UUID? {
#if DEBUG
        let arguments = ProcessInfo.processInfo.arguments
        guard let flagIndex = arguments.firstIndex(of: "-runbuoy-ui-preview-run"),
              arguments.indices.contains(flagIndex + 1)
        else {
            return nil
        }
        return UUID(uuidString: arguments[flagIndex + 1])
#else
        nil
#endif
    }
}
