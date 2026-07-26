import Foundation
import Observation
import SwiftUI

enum AppTab: String, CaseIterable, Identifiable {
    case runs
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
    var selectedTab: AppTab = .runs
    var runsPath: [AppRoute] = []
    var settingsPath: [AppRoute] = []

    func handle(_ url: URL) -> Bool {
        guard url.scheme?.lowercased() == "runbuoy",
              url.host?.lowercased() == "runs",
              let rawID = url.path.split(separator: "/").first,
              let runID = UUID(uuidString: String(rawID))
        else {
            return false
        }
        selectedTab = .runs
        runsPath = [.runDetail(runID)]
        return true
    }
}
