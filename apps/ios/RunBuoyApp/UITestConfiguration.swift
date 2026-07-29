import Foundation
import UIKit

struct UITestConfiguration {
    enum Scenario: String {
        case loaded
        case empty
        case offline
        case failed
    }

    let isEnabled: Bool
    let scenario: Scenario
    let showsOnboarding: Bool
    let initialURL: URL?

    static var current: UITestConfiguration {
#if DEBUG
        let arguments = ProcessInfo.processInfo.arguments
        let isEnabled = arguments.contains("-runbuoy-ui-testing")
        let scenario = argumentValue(
            after: "-runbuoy-ui-scenario",
            in: arguments
        ).flatMap(Scenario.init(rawValue:)) ?? .loaded
        let initialURL = argumentValue(
            after: "-runbuoy-ui-url",
            in: arguments
        ).flatMap(URL.init(string:))

        if isEnabled {
            if arguments.contains("-runbuoy-ui-reset-state") {
                resetPersistentState()
            }
            UIView.setAnimationsEnabled(false)
        }

        return UITestConfiguration(
            isEnabled: isEnabled,
            scenario: scenario,
            showsOnboarding: arguments.contains("-runbuoy-ui-onboarding"),
            initialURL: initialURL
        )
#else
        return UITestConfiguration(
            isEnabled: false,
            scenario: .loaded,
            showsOnboarding: false,
            initialURL: nil
        )
#endif
    }

#if DEBUG
    private static func argumentValue(
        after flag: String,
        in arguments: [String]
    ) -> String? {
        guard let index = arguments.firstIndex(of: flag),
              arguments.indices.contains(index + 1)
        else {
            return nil
        }
        return arguments[index + 1]
    }

    private static func resetPersistentState() {
        let defaults = UserDefaults.standard
        for key in defaults.dictionaryRepresentation().keys
        where key.hasPrefix("runbuoy.") {
            defaults.removeObject(forKey: key)
        }

        let previewCache = FileManager.default.temporaryDirectory
            .appendingPathComponent("runbuoy-preview-cache.json")
        try? FileManager.default.removeItem(at: previewCache)
    }
#endif
}
