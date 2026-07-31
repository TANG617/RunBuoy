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
    private(set) var lastRefreshAt: Date?
    private(set) var deviceIdentity: DeviceIdentity?
    private(set) var activeRunModels: [RunSummaryModel] = []
    private(set) var historyRunModels: [RunSummaryModel] = []

    private let api: any RunBuoyAPI
    private let identityStore: any DeviceIdentityStoring
    private let cache: LocalCacheStore
    private let userDefaults: UserDefaults
    @ObservationIgnored private var runModelsByID: [UUID: RunSummaryModel] = [:]

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

    func refresh() async {
        guard deviceIdentity != nil || (try? identityStore.load()) != nil else {
            state = .idle
            return
        }
        state = .loading
        do {
            async let loadedRuns = api.listRuns()
            async let loadedMachines = api.listMachines()
            async let loadedMessages = api.listMessages()
            let result = try await (loadedRuns, loadedMachines, loadedMessages)
            runs = result.0.sorted { $0.updatedAt > $1.updatedAt }
            reconcileRunModels(with: runs)
            machines = result.1.sorted { $0.lastSeenAt > $1.lastSeenAt }
            messages = result.2.sorted { $0.createdAt > $1.createdAt }
            lastRefreshAt = Date()
            state = .loaded
            try? await cache.save(
                CachedSnapshot(
                    runs: runs,
                    machines: machines,
                    messages: messages,
                    savedAt: lastRefreshAt ?? Date()
                )
            )
        } catch is CancellationError {
            return
        } catch {
            let description = error.localizedDescription
            state = runs.isEmpty && machines.isEmpty && messages.isEmpty
                ? .failed(description)
                : .offline(description)
        }
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

    func removeLocalPairing(subscriptionID: String?) async throws {
        if let subscriptionID {
            try await api.deleteSubscription(subscriptionID)
        }
        await refresh()
    }

    func clearCache() async throws {
        try await cache.clear()
        runs = []
        activeRunModels = []
        historyRunModels = []
        runModelsByID = [:]
        machines = []
        messages = []
        lastRefreshAt = nil
        state = .idle
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
