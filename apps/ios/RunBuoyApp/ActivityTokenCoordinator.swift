import ActivityKit
import Foundation

@MainActor
final class ActivityTokenCoordinator {
    private let api: any RunBuoyAPI
    private let userDefaults: UserDefaults
    private var lifecycleTasks: [Task<Void, Never>] = []
    private var activityTokenTasks: [String: Task<Void, Never>] = [:]
    private var retryTasks: [String: Task<Void, Never>] = [:]
    private var retryVersions: [String: UUID] = [:]
    private var retryFingerprints: [String: String] = [:]
    private var successfulFingerprints: [String: String] = [:]
    private var generations: [String: Int] = [:]
    private var observedTokens: [String: Data] = [:]

    init(api: any RunBuoyAPI, userDefaults: UserDefaults = .standard) {
        self.api = api
        self.userDefaults = userDefaults
    }

    func start() {
        guard lifecycleTasks.isEmpty else { return }
        reconcileCurrentActivities()

        lifecycleTasks = [
            Task { [weak self] in
                for await token in Activity<RunActivityAttributes>.pushToStartTokenUpdates {
                    guard !Task.isCancelled else { return }
                    self?.registerPushToStartToken(token)
                }
            },
            Task { [weak self] in
                for await activity in Activity<RunActivityAttributes>.activityUpdates {
                    guard !Task.isCancelled else { return }
                    if let token = activity.pushToken {
                        self?.registerUpdateToken(token, for: activity)
                    }
                    self?.observeUpdateToken(for: activity)
                    self?.syncCurrentActivities()
                }
            },
            Task { [weak self] in
                let authorization = ActivityAuthorizationInfo()
                for await _ in authorization.frequentPushEnablementUpdates {
                    guard !Task.isCancelled else { return }
                    self?.syncCurrentActivities()
                }
            }
        ]
    }

    func stop() {
        lifecycleTasks.forEach { $0.cancel() }
        lifecycleTasks = []
        activityTokenTasks.values.forEach { $0.cancel() }
        activityTokenTasks = [:]
        retryTasks.values.forEach { $0.cancel() }
        retryTasks = [:]
        retryVersions = [:]
        retryFingerprints = [:]
        successfulFingerprints = [:]
    }

    func reconcileCurrentActivities() {
        if let token = Activity<RunActivityAttributes>.pushToStartToken {
            registerPushToStartToken(token)
        }
        for activity in Activity<RunActivityAttributes>.activities {
            if let token = activity.pushToken {
                registerUpdateToken(token, for: activity)
            }
            observeUpdateToken(for: activity)
        }
        syncCurrentActivities()
    }

    func reconcile(with runs: [RunSnapshot]) async {
        let snapshots = Dictionary(uniqueKeysWithValues: runs.map { ($0.id, $0) })
        for activity in Activity<RunActivityAttributes>.activities {
            guard let runID = UUID(uuidString: activity.attributes.runID),
                  let snapshot = snapshots[runID]
            else {
                continue
            }
            let currentSequence = activity.content.state.sequence
            let content = ActivityContent(
                state: RunLiveActivityProjection.contentState(for: snapshot),
                staleDate: snapshot.executionStatus.isActive
                    ? snapshot.updatedAt.addingTimeInterval(60)
                    : nil
            )
            if snapshot.executionStatus.isActive,
               snapshot.sequence > currentSequence {
                await activity.update(content)
            } else if snapshot.executionStatus.isTerminal,
                      snapshot.sequence >= currentSequence,
                      activity.activityState != .ended,
                      activity.activityState != .dismissed {
                await activity.end(content, dismissalPolicy: .default)
            }
        }
        reconcileCurrentActivities()
    }

    private func observeUpdateToken(for activity: Activity<RunActivityAttributes>) {
        guard activityTokenTasks[activity.id] == nil else { return }
        activityTokenTasks[activity.id] = Task { [weak self] in
            for await token in activity.pushTokenUpdates {
                guard !Task.isCancelled else { return }
                self?.registerUpdateToken(token, for: activity)
            }
        }
    }

    private func syncCurrentActivities() {
        let current = Activity<RunActivityAttributes>.activities.map { activity in
            let token = activity.pushToken
            return ActivityRegistration(
                activityID: activity.id,
                runID: activity.attributes.runID,
                updateToken: token?.hexadecimalString,
                tokenGeneration: token.map { tokenData in
                    generation(for: activity.id, token: tokenData)
                } ?? 1,
                state: stateName(activity.activityState),
                lastSequence: activity.content.state.sequence
            )
        }
        let frequentPushesEnabled = ActivityAuthorizationInfo().frequentPushesEnabled
        let fingerprint = activitySyncFingerprint(
            current,
            frequentPushesEnabled: frequentPushesEnabled
        )
        scheduleRetry(key: "activity-sync", fingerprint: fingerprint) { [api] in
            try await api.syncActivities(
                current,
                frequentPushesEnabled: frequentPushesEnabled
            )
        }
    }

    private func stateName(_ state: ActivityState) -> String {
        switch state {
        case .pending: "active"
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

    private func generation(for activityID: String, token: Data) -> Int {
        if observedTokens[activityID] == token {
            return generations[activityID]
                ?? userDefaults.integer(forKey: "runbuoy.activity-generation.\(activityID)")
        }
        observedTokens[activityID] = token
        return nextGeneration(for: activityID)
    }

    private func registerUpdateToken(
        _ token: Data,
        for activity: Activity<RunActivityAttributes>
    ) {
        let generation = generation(for: activity.id, token: token)
        let tokenString = token.hexadecimalString
        let activityID = activity.id
        let runID = activity.attributes.runID
        scheduleRetry(
            key: "activity-token:\(activity.id)",
            fingerprint: String(generation)
        ) { [api] in
            try await api.registerActivityToken(
                tokenString,
                activityID: activityID,
                runID: runID,
                generation: generation
            )
        }
    }

    private func registerPushToStartToken(_ token: Data) {
        let generation = generation(for: "push-to-start", token: token)
        let tokenString = token.hexadecimalString
        scheduleRetry(key: "push-to-start", fingerprint: String(generation)) { [api] in
            try await api.registerPushToStartToken(
                tokenString,
                generation: generation
            )
        }
    }

    private func scheduleRetry(
        key: String,
        fingerprint: String,
        operation: @escaping @Sendable () async throws -> Void
    ) {
        guard retryFingerprints[key] != fingerprint,
              successfulFingerprints[key] != fingerprint
        else {
            return
        }
        retryTasks[key]?.cancel()
        let version = UUID()
        retryVersions[key] = version
        retryFingerprints[key] = fingerprint
        retryTasks[key] = Task { [weak self] in
            let succeeded = await Self.retry(operation)
            guard !Task.isCancelled, self?.retryVersions[key] == version else { return }
            if succeeded {
                self?.successfulFingerprints[key] = fingerprint
            }
            self?.retryTasks[key] = nil
            self?.retryVersions[key] = nil
            self?.retryFingerprints[key] = nil
        }
    }

    private func activitySyncFingerprint(
        _ activities: [ActivityRegistration],
        frequentPushesEnabled: Bool
    ) -> String {
        let activityValues = activities
            .sorted { $0.activityID < $1.activityID }
            .map { activity in
                [
                    activity.activityID,
                    activity.runID,
                    String(activity.tokenGeneration),
                    activity.state,
                    String(activity.lastSequence),
                    activity.updateToken == nil ? "0" : "1"
                ].joined(separator: "|")
            }
            .joined(separator: ",")
        return "\(frequentPushesEnabled ? 1 : 0):\(activityValues)"
    }

    private nonisolated static func retry(
        _ operation: @escaping @Sendable () async throws -> Void
    ) async -> Bool {
        var delay: UInt64 = 500_000_000
        for attempt in 0..<6 {
            guard !Task.isCancelled else { return false }
            do {
                try await operation()
                return true
            } catch {
                guard attempt < 5 else { return false }
                do {
                    try await Task.sleep(nanoseconds: delay)
                } catch {
                    return false
                }
                delay = min(delay * 2, 8_000_000_000)
            }
        }
        return false
    }
}

enum RunLiveActivityProjection {
    static func contentState(
        for snapshot: RunSnapshot
    ) -> RunActivityAttributes.ContentState {
        RunActivityAttributes.ContentState(
            sequence: snapshot.sequence,
            executionStatus: snapshot.executionStatus.rawValue,
            healthStatus: snapshot.healthStatus.rawValue,
            attentionStatus: snapshot.attentionStatus.rawValue,
            progressKind: snapshot.progress?.kind.rawValue ?? "indeterminate",
            progress: snapshot.progress?.fraction,
            current: snapshot.progress?.current,
            total: snapshot.progress?.total,
            phase: snapshot.phase,
            message: snapshot.safeMessage,
            createdAt: snapshot.createdAt,
            startedAt: snapshot.startedAt,
            updatedAt: snapshot.updatedAt,
            machineName: snapshot.machineName,
            endedAt: snapshot.endedAt,
            estimatedEndAt: snapshot.estimatedEndAt,
            exitCode: snapshot.exitCode
        )
    }
}

private extension Data {
    var hexadecimalString: String {
        map { String(format: "%02x", $0) }.joined()
    }
}
