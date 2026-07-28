import Foundation
import Observation
import SwiftUI

enum AppTab: String, CaseIterable, Identifiable {
    case activeRuns
    case history
    case settings

    var id: String { rawValue }
}

enum AppRoute: Hashable {
    case runDetail(UUID)
    case machines
    case machine(String)
    case pairMachine
}

@MainActor
@Observable
final class AppRouter {
    var selectedTab: AppTab = .activeRuns
    var activeRunsPath: [AppRoute] = []
    var historyPath: [AppRoute] = []
    var settingsPath: [AppRoute] = []
    var pendingPairingCode: PairingCode?

    func handle(_ url: URL) -> Bool {
        guard url.scheme?.lowercased() == "runbuoy" else {
            return false
        }

        switch url.host?.lowercased() {
        case "pair":
            guard let pairingCode = try? PairingCode.decode(url.absoluteString) else {
                return false
            }
            pendingPairingCode = pairingCode
            selectedTab = .settings
            settingsPath = [.pairMachine]
            return true
        case "runs":
            guard let rawID = url.path.split(separator: "/").first,
                  let runID = UUID(uuidString: String(rawID))
            else {
                return false
            }
            selectedTab = .activeRuns
            activeRunsPath = [.runDetail(runID)]
            return true
        default:
            return false
        }
    }

    func clearPendingPairing() {
        pendingPairingCode = nil
        settingsPath = []
    }
}
