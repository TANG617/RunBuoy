import Foundation
import XCTest
@testable import RunBuoyApp

@MainActor
final class CacheStoreTests: XCTestCase {
    func testCacheRoundTripAndClear() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent("runbuoy-cache-test-\(UUID().uuidString)", isDirectory: true)
        let fileURL = directory.appendingPathComponent("cache.json")
        let cache = LocalCacheStore(fileURL: fileURL)
        let expected = CachedSnapshot(
            runs: [PreviewFixtures.activeRun],
            machines: [PreviewFixtures.machine],
            messages: [PreviewFixtures.message],
            syncCursor: 42,
            serverTime: PreviewFixtures.baseDate,
            historyRunsNextCursor: "runs-next",
            historyRunsHasMore: true,
            historyMessagesNextCursor: "messages-next",
            historyMessagesHasMore: true,
            savedAt: PreviewFixtures.baseDate
        )

        try await cache.save(expected)
        let loaded = try await cache.load()
        XCTAssertEqual(loaded, expected)
        try await cache.clear()
        let cleared = try await cache.load()
        XCTAssertNil(cleared)
    }

    func testLegacyCacheWithoutCursorFieldsStillDecodes() throws {
        let snapshot = CachedSnapshot(
            runs: [PreviewFixtures.activeRun],
            machines: [PreviewFixtures.machine],
            messages: [PreviewFixtures.message],
            savedAt: PreviewFixtures.baseDate
        )
        var object = try XCTUnwrap(
            JSONSerialization.jsonObject(with: JSONEncoder.runBuoy.encode(snapshot)) as? [String: Any]
        )
        for key in [
            "syncCursor",
            "serverTime",
            "historyRunsNextCursor",
            "historyRunsHasMore",
            "historyMessagesNextCursor",
            "historyMessagesHasMore"
        ] {
            object.removeValue(forKey: key)
        }

        let decoded = try JSONDecoder.runBuoy.decode(
            CachedSnapshot.self,
            from: JSONSerialization.data(withJSONObject: object)
        )

        XCTAssertNil(decoded.syncCursor)
        XCTAssertFalse(decoded.historyRunsHasMore)
        XCTAssertEqual(decoded.runs, snapshot.runs)
    }

    func testStorePrefersSyncAndPersistsCursorWithSnapshot() async throws {
        let cache = makeCache()
        let api = StoreAPIStub(
            syncResult: .snapshot(
                SyncSnapshot(
                    nextCursor: 7,
                    serverTime: PreviewFixtures.baseDate,
                    runs: [PreviewFixtures.activeRun],
                    machines: [PreviewFixtures.machine],
                    notifications: [PreviewFixtures.message]
                )
            )
        )
        let store = makeStore(api: api, cache: cache)

        let succeeded = await store.refresh()
        let counts = await api.callCounts()

        XCTAssertTrue(succeeded)
        XCTAssertEqual(store.syncCursor, 7)
        XCTAssertEqual(store.runs, [PreviewFixtures.activeRun])
        let cached = try await cache.load()
        XCTAssertEqual(cached?.syncCursor, 7)
        XCTAssertEqual(cached?.runs, [PreviewFixtures.activeRun])
        XCTAssertEqual(counts.sync, 1)
        XCTAssertEqual(counts.legacy, 0)
    }

    func testOldServerFallsBackToLegacyCollections() async {
        let api = StoreAPIStub(
            syncErrorStatus: 404,
            legacyRuns: [PreviewFixtures.activeRun],
            legacyMachines: [PreviewFixtures.machine],
            legacyMessages: [PreviewFixtures.message]
        )
        let store = makeStore(api: api, cache: makeCache())

        let succeeded = await store.refresh()
        let counts = await api.callCounts()

        XCTAssertTrue(succeeded)
        XCTAssertNil(store.syncCursor)
        XCTAssertFalse(store.supportsHistoryPagination)
        XCTAssertEqual(store.runs, [PreviewFixtures.activeRun])
        XCTAssertEqual(counts.legacy, 3)
    }

    func testOfflineRefreshKeepsColdCacheVisible() async {
        let initial = CachedSnapshot(
            runs: [PreviewFixtures.activeRun],
            machines: [PreviewFixtures.machine],
            messages: [PreviewFixtures.message],
            syncCursor: 4,
            savedAt: PreviewFixtures.baseDate
        )
        let api = StoreAPIStub(syncErrorStatus: 503)
        let store = makeStore(api: api, cache: makeCache(), initialSnapshot: initial)

        let succeeded = await store.refresh()

        XCTAssertFalse(succeeded)
        XCTAssertEqual(store.runs, initial.runs)
        guard case .offline = store.state else {
            return XCTFail("Expected cached offline state")
        }
    }

    func testConcurrentRefreshesCoalesceIntoOneSyncRequest() async {
        let api = StoreAPIStub(
            syncResult: .snapshot(
                SyncSnapshot(
                    nextCursor: 1,
                    serverTime: PreviewFixtures.baseDate,
                    runs: [],
                    machines: [],
                    notifications: []
                )
            ),
            delayNanoseconds: 50_000_000
        )
        let store = makeStore(api: api, cache: makeCache())

        async let first = store.refresh()
        async let second = store.refresh()
        let results = await (first, second)

        XCTAssertTrue(results.0)
        XCTAssertTrue(results.1)
        let counts = await api.callCounts()
        XCTAssertEqual(counts.sync, 1)
    }

    func testLowerSequenceSyncSnapshotCannotRegressCachedRun() async {
        let current = PreviewFixtures.activeRun
        let stale = runSnapshot(basedOn: current, sequence: current.sequence - 1)
        let initial = CachedSnapshot(
            runs: [current],
            machines: [],
            messages: [],
            syncCursor: 4,
            savedAt: PreviewFixtures.baseDate
        )
        let api = StoreAPIStub(
            syncResult: .snapshot(
                SyncSnapshot(
                    nextCursor: 5,
                    serverTime: PreviewFixtures.baseDate,
                    runs: [stale],
                    machines: [],
                    notifications: []
                )
            )
        )
        let store = makeStore(api: api, cache: makeCache(), initialSnapshot: initial)

        let succeeded = await store.refresh()

        XCTAssertTrue(succeeded)
        XCTAssertEqual(store.runs.first?.sequence, current.sequence)
    }

    func testHistoryLoadMoreMergesWithoutDuplicates() async {
        let initial = CachedSnapshot(
            runs: [PreviewFixtures.failedRun],
            machines: [],
            messages: [],
            syncCursor: 4,
            historyRunsNextCursor: "next-page",
            historyRunsHasMore: true,
            savedAt: PreviewFixtures.baseDate
        )
        let additional = runSnapshot(
            basedOn: PreviewFixtures.failedRun,
            id: UUID(),
            sequence: PreviewFixtures.failedRun.sequence
        )
        let api = StoreAPIStub(
            historyRunPage: HistoryPage(
                items: [PreviewFixtures.failedRun, additional],
                nextCursor: nil,
                hasMore: false
            )
        )
        let store = makeStore(api: api, cache: makeCache(), initialSnapshot: initial)

        await store.loadMoreHistoryRuns(machineID: nil)

        XCTAssertEqual(
            Set(store.runs.map(\.id)),
            Set([PreviewFixtures.failedRun.id, additional.id])
        )
        XCTAssertFalse(store.canLoadMoreRuns(machineID: nil))
    }

    func testAdaptiveRefreshCadenceAndBackoff() {
        XCTAssertEqual(RefreshCadence.interval(hasActiveRuns: true, consecutiveFailures: 0), 10)
        XCTAssertEqual(RefreshCadence.interval(hasActiveRuns: false, consecutiveFailures: 0), 30)
        XCTAssertEqual(RefreshCadence.interval(hasActiveRuns: true, consecutiveFailures: 1), 20)
        XCTAssertEqual(RefreshCadence.interval(hasActiveRuns: false, consecutiveFailures: 2), 120)
        XCTAssertEqual(RefreshCadence.interval(hasActiveRuns: true, consecutiveFailures: 20), 300)
    }

    func testServerResetFailureKeepsIdentityCacheAndDefaults() async throws {
        let cache = makeCache()
        try await cache.save(
            CachedSnapshot(
                runs: [PreviewFixtures.activeRun],
                machines: [PreviewFixtures.machine],
                messages: [],
                savedAt: PreviewFixtures.baseDate
            )
        )
        let identityStore = CacheTestIdentityStore()
        let defaults = UserDefaults(suiteName: "runbuoy-reset-failure-\(UUID().uuidString)")!
        defaults.set(true, forKey: "runbuoy.test-value")
        let store = RunBuoyStore(
            api: StoreAPIStub(resetErrorStatus: 503),
            identityStore: identityStore,
            cache: cache,
            userDefaults: defaults
        )

        do {
            try await store.resetDevice()
            XCTFail("Expected server reset failure")
        } catch {
            XCTAssertEqual(error as? APIError, .httpStatus(503))
        }

        XCTAssertNotNil(try identityStore.load())
        let retainedCache = try await cache.load()
        XCTAssertNotNil(retainedCache)
        XCTAssertTrue(defaults.bool(forKey: "runbuoy.test-value"))
    }

    func testServerResetSuccessClearsIdentityCacheAndRunBuoyDefaults() async throws {
        let cache = makeCache()
        try await cache.save(
            CachedSnapshot(
                runs: [PreviewFixtures.activeRun],
                machines: [PreviewFixtures.machine],
                messages: [],
                savedAt: PreviewFixtures.baseDate
            )
        )
        let identityStore = CacheTestIdentityStore()
        let defaults = UserDefaults(suiteName: "runbuoy-reset-success-\(UUID().uuidString)")!
        defaults.set(true, forKey: "runbuoy.test-value")
        defaults.set(true, forKey: "unrelated.test-value")
        let store = RunBuoyStore(
            api: StoreAPIStub(),
            identityStore: identityStore,
            cache: cache,
            userDefaults: defaults,
            initialSnapshot: try await cache.load()
        )

        try await store.resetDevice()

        XCTAssertNil(try identityStore.load())
        let clearedCache = try await cache.load()
        XCTAssertNil(clearedCache)
        XCTAssertNil(defaults.object(forKey: "runbuoy.test-value"))
        XCTAssertTrue(defaults.bool(forKey: "unrelated.test-value"))
        XCTAssertNil(store.deviceIdentity)
        XCTAssertTrue(store.runs.isEmpty)
    }

    private func makeCache() -> LocalCacheStore {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("runbuoy-store-test-\(UUID().uuidString)")
            .appendingPathComponent("cache.json")
        return LocalCacheStore(fileURL: url)
    }

    private func makeStore(
        api: StoreAPIStub,
        cache: LocalCacheStore,
        initialSnapshot: CachedSnapshot? = nil
    ) -> RunBuoyStore {
        RunBuoyStore(
            api: api,
            identityStore: CacheTestIdentityStore(),
            cache: cache,
            initialSnapshot: initialSnapshot
        )
    }

    private func runSnapshot(
        basedOn snapshot: RunSnapshot,
        id: UUID? = nil,
        sequence: Int
    ) -> RunSnapshot {
        RunSnapshot(
            id: id ?? snapshot.id,
            machineID: snapshot.machineID,
            machineName: snapshot.machineName,
            title: snapshot.title,
            source: snapshot.source,
            executionStatus: snapshot.executionStatus,
            healthStatus: snapshot.healthStatus,
            attentionStatus: snapshot.attentionStatus,
            progress: snapshot.progress,
            phase: snapshot.phase,
            safeMessage: snapshot.safeMessage,
            createdAt: snapshot.createdAt,
            startedAt: snapshot.startedAt,
            updatedAt: snapshot.updatedAt,
            endedAt: snapshot.endedAt,
            estimatedEndAt: snapshot.estimatedEndAt,
            exitCode: snapshot.exitCode,
            safeLogTail: snapshot.safeLogTail,
            sequence: sequence
        )
    }
}

private final class CacheTestIdentityStore: DeviceIdentityStoring, @unchecked Sendable {
    private let lock = NSLock()
    private var identity: DeviceIdentity? = DeviceIdentity(
        deviceID: "device",
        workspaceID: "workspace",
        credential: "credential"
    )

    func load() throws -> DeviceIdentity? {
        lock.withLock { identity }
    }
    func save(_ identity: DeviceIdentity) throws {
        lock.withLock { self.identity = identity }
    }
    func remove() throws {
        lock.withLock { identity = nil }
    }
}

private actor StoreAPIStub: RunBuoyAPI {
    private let syncResult: SyncResult
    private let syncErrorStatus: Int?
    private let legacyRuns: [RunSnapshot]
    private let legacyMachines: [MachineSnapshot]
    private let legacyMessages: [RichMessage]
    private let historyRunPage: HistoryPage<RunSnapshot>
    private let historyMessagePage: HistoryPage<RichMessage>
    private let delayNanoseconds: UInt64
    private let resetErrorStatus: Int?
    private var syncCalls = 0
    private var legacyCalls = 0

    init(
        syncResult: SyncResult = .notModified,
        syncErrorStatus: Int? = nil,
        legacyRuns: [RunSnapshot] = [],
        legacyMachines: [MachineSnapshot] = [],
        legacyMessages: [RichMessage] = [],
        historyRunPage: HistoryPage<RunSnapshot> = HistoryPage(
            items: [], nextCursor: nil, hasMore: false
        ),
        historyMessagePage: HistoryPage<RichMessage> = HistoryPage(
            items: [], nextCursor: nil, hasMore: false
        ),
        delayNanoseconds: UInt64 = 0,
        resetErrorStatus: Int? = nil
    ) {
        self.syncResult = syncResult
        self.syncErrorStatus = syncErrorStatus
        self.legacyRuns = legacyRuns
        self.legacyMachines = legacyMachines
        self.legacyMessages = legacyMessages
        self.historyRunPage = historyRunPage
        self.historyMessagePage = historyMessagePage
        self.delayNanoseconds = delayNanoseconds
        self.resetErrorStatus = resetErrorStatus
    }

    func callCounts() -> (sync: Int, legacy: Int) {
        (syncCalls, legacyCalls)
    }

    func bootstrap(installationID: String, appVersion: String, osVersion: String) async throws -> DeviceIdentity {
        DeviceIdentity(deviceID: "device", workspaceID: "workspace", credential: "credential")
    }

    func sync(cursor: Int?) async throws -> SyncResult {
        syncCalls += 1
        if delayNanoseconds > 0 {
            try await Task.sleep(nanoseconds: delayNanoseconds)
        }
        if let syncErrorStatus {
            throw APIError.httpStatus(syncErrorStatus)
        }
        return syncResult
    }

    func listRuns() async throws -> [RunSnapshot] {
        legacyCalls += 1
        return legacyRuns
    }
    func runDetail(id: UUID) async throws -> RunDetail {
        RunDetail(run: legacyRuns[0], feed: [])
    }
    func listMachines() async throws -> [MachineSnapshot] {
        legacyCalls += 1
        return legacyMachines
    }
    func listMessages() async throws -> [RichMessage] {
        legacyCalls += 1
        return legacyMessages
    }
    func historyRuns(
        cursor: String?,
        limit: Int,
        machineID: String?
    ) async throws -> HistoryPage<RunSnapshot> {
        historyRunPage
    }
    func historyMessages(
        cursor: String?,
        limit: Int,
        machineID: String?
    ) async throws -> HistoryPage<RichMessage> {
        historyMessagePage
    }
    func claimPairing(_ code: PairingCode) async throws {}
    func registerNotificationToken(_ token: String) async throws {}
    func registerPushToStartToken(_ token: String, generation: Int) async throws {}
    func registerActivityToken(
        _ token: String,
        activityID: String,
        runID: String,
        generation: Int
    ) async throws {}
    func syncActivities(
        _ activities: [ActivityRegistration],
        frequentPushesEnabled: Bool
    ) async throws {}
    func updatePreferences(_ preferences: DevicePreferences) async throws {}
    func deleteSubscription(_ id: String) async throws {}
    func resetDevice() async throws {
        if let resetErrorStatus {
            throw APIError.httpStatus(resetErrorStatus)
        }
    }
    func revokeMachine(_ id: String) async throws {}
    func requestWorkspaceDeletionChallenge() async throws -> WorkspaceDeletionChallenge {
        WorkspaceDeletionChallenge(challenge: "challenge", expiresAt: Date.distantFuture)
    }
    func deleteWorkspace(challenge: String) async throws {}
}
