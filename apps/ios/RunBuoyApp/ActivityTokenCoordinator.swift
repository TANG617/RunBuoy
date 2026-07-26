import ActivityKit
import Foundation

@MainActor
final class ActivityTokenCoordinator {
    private let api: any RunBuoyAPI
    private let userDefaults: UserDefaults
    private var lifecycleTasks: [Task<Void, Never>] = []
    private var activityTokenTasks: [String: Task<Void, Never>] = [:]
    private var generations: [String: Int] = [:]

    init(api: any RunBuoyAPI, userDefaults: UserDefaults = .standard) {
        self.api = api
        self.userDefaults = userDefaults
    }

    func start() {
        guard lifecycleTasks.isEmpty else { return }
        reconcileCurrentActivities()
        if let token = Activity<RunActivityAttributes>.pushToStartToken {
            Task { try? await api.registerPushToStartToken(token.hexadecimalString) }
        }

        lifecycleTasks = [
            Task { [weak self] in
                for await token in Activity<RunActivityAttributes>.pushToStartTokenUpdates {
                    guard !Task.isCancelled else { return }
                    try? await self?.api.registerPushToStartToken(token.hexadecimalString)
                }
            },
            Task { [weak self] in
                for await activity in Activity<RunActivityAttributes>.activityUpdates {
                    guard !Task.isCancelled else { return }
                    self?.observeUpdateToken(for: activity)
                    await self?.syncCurrentActivities()
                }
            }
        ]
    }

    func stop() {
        lifecycleTasks.forEach { $0.cancel() }
        lifecycleTasks = []
        activityTokenTasks.values.forEach { $0.cancel() }
        activityTokenTasks = [:]
    }

    func reconcileCurrentActivities() {
        for activity in Activity<RunActivityAttributes>.activities {
            observeUpdateToken(for: activity)
        }
        Task { await syncCurrentActivities() }
    }

    private func observeUpdateToken(for activity: Activity<RunActivityAttributes>) {
        guard activityTokenTasks[activity.id] == nil else { return }
        activityTokenTasks[activity.id] = Task { [weak self] in
            for await token in activity.pushTokenUpdates {
                guard !Task.isCancelled else { return }
                let generation = await self?.nextGeneration(for: activity.id) ?? 1
                try? await self?.api.registerActivityToken(
                    token.hexadecimalString,
                    activityID: activity.id,
                    runID: activity.attributes.runID,
                    generation: generation
                )
            }
        }
    }

    private func syncCurrentActivities() async {
        let current = Activity<RunActivityAttributes>.activities.map {
            ActivityRegistration(
                activityID: $0.id,
                runID: $0.attributes.runID,
                state: stateName($0.activityState),
                lastSequence: $0.content.state.sequence
            )
        }
        try? await api.syncActivities(current)
    }

    private func stateName(_ state: ActivityState) -> String {
        switch state {
        case .active: "active"
        case .dismissed: "dismissed"
        case .ended: "ended"
        case .stale: "stale"
        @unknown default: "active"
        }
    }

    private func nextGeneration(for activityID: String) -> Int {
        let key = "runbuoy.activity-generation.\(activityID)"
        let stored = userDefaults.integer(forKey: key)
        let next = max(generations[activityID] ?? 0, stored) + 1
        generations[activityID] = next
        userDefaults.set(next, forKey: key)
        return next
    }
}

private extension Data {
    var hexadecimalString: String {
        map { String(format: "%02x", $0) }.joined()
    }
}
