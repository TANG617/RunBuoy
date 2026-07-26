import Foundation
import UIKit
import UserNotifications

@MainActor
final class NotificationCoordinator: NSObject, UNUserNotificationCenterDelegate {
    var onDeviceToken: ((String) -> Void)?
    var onRefreshRequested: (() -> Void)?
    private var pendingDeviceToken: String?

    func configure() {
        UNUserNotificationCenter.current().delegate = self
        if let pendingDeviceToken {
            onDeviceToken?(pendingDeviceToken)
            self.pendingDeviceToken = nil
        }
    }

    func requestAuthorization() async throws -> Bool {
        let center = UNUserNotificationCenter.current()
        let granted = try await center.requestAuthorization(options: [.alert, .badge, .sound])
        if granted {
            UIApplication.shared.registerForRemoteNotifications()
        }
        return granted
    }

    func receive(deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        if let onDeviceToken {
            onDeviceToken(token)
        } else {
            pendingDeviceToken = token
        }
    }

    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        await MainActor.run { onRefreshRequested?() }
        return [.banner, .sound]
    }

    nonisolated func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse
    ) async {
        await MainActor.run { onRefreshRequested?() }
    }
}

final class RunBuoyAppDelegate: NSObject, UIApplicationDelegate {
    var onDeviceToken: ((Data) -> Void)?
    private var pendingToken: Data?

    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        if let onDeviceToken {
            onDeviceToken(deviceToken)
        } else {
            pendingToken = deviceToken
        }
    }

    func installTokenHandler(_ handler: @escaping (Data) -> Void) {
        onDeviceToken = handler
        if let pendingToken {
            handler(pendingToken)
            self.pendingToken = nil
        }
    }
}
