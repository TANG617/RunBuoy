import Foundation
import Observation
import SwiftUI

enum AppTab: String, CaseIterable, Identifiable {
    case activeRuns
    case history
    case machines
    case settings

    var id: String { rawValue }
}

enum AppRoute: Hashable {
    case runDetail(UUID)
    case machine(String)
}

@MainActor
@Observable
final class AppRouter {
    var selectedTab: AppTab = .activeRuns
    var activeRunsPath: [AppRoute] = []
    var historyPath: [AppRoute] = []
    var machinesPath: [AppRoute] = []
    var settingsPath: [AppRoute] = []

    func handle(_ url: URL) -> Bool {
        guard url.scheme?.lowercased() == "runbuoy",
              url.host?.lowercased() == "runs",
              let rawID = url.path.split(separator: "/").first,
              let runID = UUID(uuidString: String(rawID))
        else {
            return false
        }
        selectedTab = .activeRuns
        activeRunsPath = [.runDetail(runID)]
        return true
    }

    func showMachines() {
        selectedTab = .machines
    }
}
