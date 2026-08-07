import Foundation
import Observation
import UIKit

@MainActor
@Observable
final class RunSummaryModel: Identifiable {
    let id: UUID
    private(set) var snapshot: RunSnapshot

    init(snapshot: RunSnapshot) {
        id = snapshot.id
        self.snapshot = snapshot
    }

    func update(with snapshot: RunSnapshot) {
        guard self.snapshot != snapshot else { return }
        self.snapshot = snapshot
    }
}

@MainActor
@Observable
final class RunBuoyStore {
    enum LoadState: Equatable {
        case idle
        case loading
        case loaded
        case offline(String)
        case failed(String)
    }

    private(set) var runs: [RunSnapshot] = []
    private(set) var machines: [MachineSnapshot] = []
    private(set) var messages: [RichMessage] = []
    private(set) var state: LoadState = .idle
    private(set) var isRefreshing = false
    private(set) var lastRefreshAt: Date?
    private(set) var serverTime: Date?
    private(set) var syncCursor: Int?
    private(set) var deviceIdentity: DeviceIdentity?
    private(set) var activeRunModels: [RunSummaryModel] = []
    private(set) var historyRunModels: [RunSummaryModel] = []
    private(set) var supportsHistoryPagination = false
    private(set) var isLoadingMoreRuns = false
    private(set) var isLoadingMoreMessages = false
    private(set) var consecutiveRefreshFailures = 0

    private let api: any RunBuoyAPI
    private let identityStore: any DeviceIdentityStoring
    private let cache: LocalCacheStore
    private let userDefaults: UserDefaults
    @ObservationIgnored private var refreshTask: Task<Bool, Never>?
    @ObservationIgnored private var runModelsByID: [UUID: RunSummaryModel] = [:]
    @ObservationIgnored private var historyRunCursors: [String: HistoryCursorState] = [:]
    @ObservationIgnored private var historyMessageCursors: [String: HistoryCursorState] = [:]

    init(
        api: any RunBuoyAPI,
        identityStore: any DeviceIdentityStoring,
        cache: LocalCacheStore,
        userDefaults: UserDefaults = .standard,
        initialSnapshot: CachedSnapshot? = nil,
        initialState: LoadState? = nil
    ) {
        self.api = api
        self.identityStore = identityStore
        self.cache = cache
        self.userDefaults = userDefaults
        MachineNameMigration.removeLegacyLocalLabels(userDefaults: userDefaults)
        deviceIdentity = try? identityStore.load()
        if let initialSnapshot {
            runs = initialSnapshot.runs
            machines = initialSnapshot.machines
            messages = initialSnapshot.messages
            syncCursor = initialSnapshot.syncCursor
            serverTime = initialSnapshot.serverTime
            supportsHistoryPagination = initialSnapshot.syncCursor != nil
            historyRunCursors[Self.historyKey(nil)] = HistoryCursorState(
                cursor: initialSnapshot.historyRunsNextCursor,
                hasMore: initialSnapshot.historyRunsHasMore
            )
            historyMessageCursors[Self.historyKey(nil)] = HistoryCursorState(
                cursor: initialSnapshot.historyMessagesNextCursor,
                hasMore: initialSnapshot.historyMessagesHasMore
            )
            lastRefreshAt = initialSnapshot.savedAt
            state = initialState ?? .loaded
            reconcileRunModels(with: initialSnapshot.runs)
        } else if let initialState {
            state = initialState
        }
    }

    func restoreCache() async {
        guard let snapshot = try? await cache.load() else { return }
        runs = snapshot.runs
        reconcileRunModels(with: snapshot.runs)
        machines = snapshot.machines
        messages = snapshot.messages
        syncCursor = snapshot.syncCursor
        serverTime = snapshot.serverTime
        supportsHistoryPagination = snapshot.syncCursor != nil
        historyRunCursors[Self.historyKey(nil)] = HistoryCursorState(
            cursor: snapshot.historyRunsNextCursor,
            hasMore: snapshot.historyRunsHasMore
        )
        historyMessageCursors[Self.historyKey(nil)] = HistoryCursorState(
            cursor: snapshot.historyMessagesNextCursor,
            hasMore: snapshot.historyMessagesHasMore
        )
        lastRefreshAt = snapshot.savedAt
        state = .offline(String(localized: "runs.offline_cache"))
    }

    @discardableResult
    func bootstrapDevice() async throws -> DeviceIdentity {
        if let deviceIdentity {
            return deviceIdentity
        }

        let installationKey = "runbuoy.installation-id"
        let installationID: String
        if let existing = userDefaults.string(forKey: installationKey) {
            installationID = existing
        } else {
            installationID = UUID().uuidString.lowercased()
            userDefaults.set(installationID, forKey: installationKey)
        }

        let appVersion = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "1"
        let identity = try await api.bootstrap(
            installationID: installationID,
            appVersion: appVersion,
            osVersion: UIDevice.current.systemVersion
        )
        try identityStore.save(identity)
        deviceIdentity = identity
        return identity
    }

    @discardableResult
    func refresh() async -> Bool {
        if let refreshTask {
            return await refreshTask.value
        }

        let task = Task { @MainActor [weak self] in
            guard let self else { return false }
            return await self.performRefresh()
        }
        refreshTask = task
        let succeeded = await task.value
        refreshTask = nil
        return succeeded
    }

    private func performRefresh() async -> Bool {
        guard deviceIdentity != nil || (try? identityStore.load()) != nil else {
            state = .idle
            return false
        }

        let stateBeforeRefresh = state
        isRefreshing = true
        if state == .idle {
            state = .loading
        }
        defer { isRefreshing = false }

        do {
            do {
                let result = try await api.sync(cursor: syncCursor)
                switch result {
                case .notModified:
                    break
                case .snapshot(let snapshot):
                    guard snapshot.schemaVersion == 1 else { throw APIError.invalidResponse }
                    apply(snapshot)
                }
                supportsHistoryPagination = true
            } catch let error as APIError where error.isSyncUnsupported {
                try await performLegacyRefresh()
            }
            consecutiveRefreshFailures = 0
            lastRefreshAt = Date()
            state = .loaded
            await saveCache()
            return true
        } catch is CancellationError {
            state = stateBeforeRefresh
            return false
        } catch {
            consecutiveRefreshFailures += 1
            let description = error.localizedDescription
            state = runs.isEmpty && machines.isEmpty && messages.isEmpty
                ? .failed(description)
                : .offline(description)
            return false
        }
    }

    private func performLegacyRefresh() async throws {
        async let loadedRuns = api.listRuns()
        async let loadedMachines = api.listMachines()
        async let loadedMessages = api.listMessages()
        let result = try await (loadedRuns, loadedMachines, loadedMessages)
        runs = Self.mergeRuns(current: runs, incoming: result.0, retainsOlderHistory: false)
        reconcileRunModels(with: runs)
        machines = result.1.sorted { $0.lastSeenAt > $1.lastSeenAt }
        messages = result.2.sorted { $0.createdAt > $1.createdAt }
        syncCursor = nil
        serverTime = nil
        supportsHistoryPagination = false
        historyRunCursors = [:]
        historyMessageCursors = [:]
    }

    private func apply(_ snapshot: SyncSnapshot) {
        runs = Self.mergeRuns(current: runs, incoming: snapshot.runs, retainsOlderHistory: true)
        reconcileRunModels(with: runs)
        machines = snapshot.machines.sorted { $0.lastSeenAt > $1.lastSeenAt }
        messages = Self.mergeMessages(
            current: messages,
            incoming: snapshot.notifications,
            serverTime: snapshot.serverTime
        )
        syncCursor = snapshot.nextCursor
        serverTime = snapshot.serverTime
        historyRunCursors[Self.historyKey(nil)] = HistoryCursorState(
            cursor: snapshot.historyRunsNextCursor,
            hasMore: snapshot.historyRunsHasMore
        )
        historyMessageCursors[Self.historyKey(nil)] = HistoryCursorState(
            cursor: snapshot.historyNotificationsNextCursor,
            hasMore: snapshot.historyNotificationsHasMore
        )
    }

    var automaticRefreshInterval: TimeInterval {
        RefreshCadence.interval(
            hasActiveRuns: !activeRunModels.isEmpty,
            consecutiveFailures: consecutiveRefreshFailures
        )
    }

    func canLoadMoreRuns(machineID: String?) -> Bool {
        guard supportsHistoryPagination else { return false }
        return historyRunCursors[Self.historyKey(machineID)]?.hasMore ?? (machineID != nil)
    }

    func canLoadMoreMessages(machineID: String?) -> Bool {
        guard supportsHistoryPagination else { return false }
        return historyMessageCursors[Self.historyKey(machineID)]?.hasMore ?? (machineID != nil)
    }

    func loadMoreHistoryRuns(machineID: String?) async {
        guard canLoadMoreRuns(machineID: machineID), !isLoadingMoreRuns else { return }
        isLoadingMoreRuns = true
        defer { isLoadingMoreRuns = false }
        let key = Self.historyKey(machineID)
        var pagination = historyRunCursors[key]
            ?? HistoryCursorState(cursor: nil, hasMore: true)
        let existingIDs = Set(runs.map(\.id))
        do {
            for _ in 0..<5 where pagination.hasMore {
                let page = try await api.historyRuns(
                    cursor: pagination.cursor,
                    limit: 50,
                    machineID: machineID
                )
                pagination = HistoryCursorState(
                    cursor: page.nextCursor,
                    hasMore: page.hasMore
                )
                runs = Self.mergeRuns(
                    current: runs,
                    incoming: page.items,
                    retainsOlderHistory: true
                )
                if !Set(runs.map(\.id)).isSubset(of: existingIDs) || !pagination.hasMore {
                    break
                }
            }
            historyRunCursors[key] = pagination
            reconcileRunModels(with: runs)
            await saveCache()
        } catch let error as APIError where error.isSyncUnsupported {
            supportsHistoryPagination = false
        } catch {
            state = .offline(error.localizedDescription)
        }
    }

    func loadMoreHistoryMessages(machineID: String?) async {
        guard canLoadMoreMessages(machineID: machineID), !isLoadingMoreMessages else { return }
        isLoadingMoreMessages = true
        defer { isLoadingMoreMessages = false }
        let key = Self.historyKey(machineID)
        var pagination = historyMessageCursors[key]
            ?? HistoryCursorState(cursor: nil, hasMore: true)
        let existingIDs = Set(messages.map(\.id))
        do {
            for _ in 0..<5 where pagination.hasMore {
                let page = try await api.historyMessages(
                    cursor: pagination.cursor,
                    limit: 50,
                    machineID: machineID
                )
                pagination = HistoryCursorState(
                    cursor: page.nextCursor,
                    hasMore: page.hasMore
                )
                messages = Self.mergeMessages(
                    current: messages,
                    incoming: page.items,
                    serverTime: serverTime ?? Date()
                )
                if !Set(messages.map(\.id)).isSubset(of: existingIDs) || !pagination.hasMore {
                    break
                }
            }
            historyMessageCursors[key] = pagination
            await saveCache()
        } catch let error as APIError where error.isSyncUnsupported {
            supportsHistoryPagination = false
        } catch {
            state = .offline(error.localizedDescription)
        }
    }

    private func saveCache() async {
        let savedAt = lastRefreshAt ?? Date()
        let runHistory = historyRunCursors[Self.historyKey(nil)]
        let messageHistory = historyMessageCursors[Self.historyKey(nil)]
        try? await cache.save(
            CachedSnapshot(
                runs: runs,
                machines: machines,
                messages: messages,
                syncCursor: syncCursor,
                serverTime: serverTime,
                historyRunsNextCursor: runHistory?.cursor,
                historyRunsHasMore: runHistory?.hasMore ?? false,
                historyMessagesNextCursor: messageHistory?.cursor,
                historyMessagesHasMore: messageHistory?.hasMore ?? false,
                savedAt: savedAt
            )
        )
    }

    func detail(for id: UUID) async throws -> RunDetail {
        try await api.runDetail(id: id)
    }

    func claim(_ code: PairingCode) async throws {
        try code.requireSelectedRegion()
        try await api.claimPairing(code)
        await refresh()
    }

    func savePreferences(_ preferences: DevicePreferences) async {
        try? await api.updatePreferences(preferences)
    }

    func stopReceiving(subscriptionID: String) async throws {
        try await api.deleteSubscription(subscriptionID)
        await refresh()
    }

    func revokeMachine(machineID: String) async throws {
        try await api.revokeMachine(machineID)
        await refresh()
    }

    func resetDevice() async throws {
        try await api.resetDevice()
        try await clearLocalIdentityAndData()
    }

    func resetDeviceLocalOnly() async throws {
        try await clearLocalIdentityAndData()
    }

    func deleteWorkspace() async throws {
        let deletionChallenge = try await api.requestWorkspaceDeletionChallenge()
        try await api.deleteWorkspace(challenge: deletionChallenge.challenge)
        try await clearLocalIdentityAndData()
    }

    func clearCache() async throws {
        try await cache.clear()
        clearInMemoryState()
    }

    private func clearLocalIdentityAndData() async throws {
        var firstError: Error?
        do {
            try await cache.clear()
        } catch {
            firstError = error
        }
        do {
            try identityStore.remove()
        } catch {
            firstError = firstError ?? error
        }
        for key in userDefaults.dictionaryRepresentation().keys where key.hasPrefix("runbuoy.") {
            userDefaults.removeObject(forKey: key)
        }
        clearInMemoryState()
        deviceIdentity = nil
        if let firstError {
            throw firstError
        }
    }

    private func clearInMemoryState() {
        runs = []
        activeRunModels = []
        historyRunModels = []
        runModelsByID = [:]
        machines = []
        messages = []
        syncCursor = nil
        serverTime = nil
        supportsHistoryPagination = false
        historyRunCursors = [:]
        historyMessageCursors = [:]
        consecutiveRefreshFailures = 0
        lastRefreshAt = nil
        state = .idle
    }

    private static func historyKey(_ machineID: String?) -> String {
        machineID ?? "__all__"
    }

    private static func mergeRuns(
        current: [RunSnapshot],
        incoming: [RunSnapshot],
        retainsOlderHistory: Bool
    ) -> [RunSnapshot] {
        let currentByID = Dictionary(uniqueKeysWithValues: current.map { ($0.id, $0) })
        var byID: [UUID: RunSnapshot] = [:]
        if retainsOlderHistory {
            for snapshot in current where snapshot.executionStatus.isTerminal {
                byID[snapshot.id] = snapshot
            }
        }
        for snapshot in incoming {
            if let existing = currentByID[snapshot.id], existing.sequence > snapshot.sequence {
                byID[snapshot.id] = existing
                continue
            }
            byID[snapshot.id] = snapshot
        }
        return byID.values.sorted {
            if $0.updatedAt == $1.updatedAt { return $0.id.uuidString > $1.id.uuidString }
            return $0.updatedAt > $1.updatedAt
        }
    }

    private static func mergeMessages(
        current: [RichMessage],
        incoming: [RichMessage],
        serverTime: Date
    ) -> [RichMessage] {
        var byID = Dictionary(uniqueKeysWithValues: current.map { ($0.id, $0) })
        for message in incoming {
            byID[message.id] = message
        }
        return byID.values
            .filter { $0.expiresAt.map { $0 > serverTime } ?? true }
            .sorted {
                if $0.createdAt == $1.createdAt { return $0.id > $1.id }
                return $0.createdAt > $1.createdAt
            }
    }

    private func reconcileRunModels(with snapshots: [RunSnapshot]) {
        var active: [RunSummaryModel] = []
        var history: [RunSummaryModel] = []
        var retainedModels: [UUID: RunSummaryModel] = [:]

        for snapshot in snapshots.sorted(by: { $0.updatedAt > $1.updatedAt }) {
            let model = runModelsByID[snapshot.id] ?? RunSummaryModel(snapshot: snapshot)
            model.update(with: snapshot)
            retainedModels[snapshot.id] = model
            if snapshot.executionStatus.isActive {
                active.append(model)
            } else {
                history.append(model)
            }
        }

        if activeRunModels.map(\.id) != active.map(\.id) {
            activeRunModels = active
        }
        if historyRunModels.map(\.id) != history.map(\.id) {
            historyRunModels = history
        }
        runModelsByID = retainedModels
    }
}

private struct HistoryCursorState {
    let cursor: String?
    let hasMore: Bool
}

enum RefreshCadence {
    static let activeInterval: TimeInterval = 10
    static let idleInterval: TimeInterval = 30
    static let maximumBackoff: TimeInterval = 5 * 60

    static func interval(hasActiveRuns: Bool, consecutiveFailures: Int) -> TimeInterval {
        let base = hasActiveRuns ? activeInterval : idleInterval
        guard consecutiveFailures > 0 else { return base }
        let multiplier = pow(2, Double(min(consecutiveFailures, 8)))
        return min(base * multiplier, maximumBackoff)
    }
}
