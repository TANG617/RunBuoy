import Foundation

enum PreviewFixtures {
    static let baseDate = Date(timeIntervalSince1970: 1_785_076_800)

    static let activeRun = RunSnapshot(
        id: UUID(uuidString: "018f0d8a-8c0a-7000-8000-000000000001")!,
        machineID: "machine_mac_studio",
        machineName: "Mac Studio",
        title: "Gurobi experiment",
        source: "cli",
        executionStatus: .running,
        healthStatus: .healthy,
        attentionStatus: .none,
        progress: RunProgress(
            kind: .determinate,
            current: 72,
            total: 100,
            fraction: 0.72,
            unit: "items",
            source: "explicit"
        ),
        phase: "Optimizing",
        safeMessage: "Solver gap reached 2.1%.",
        startedAt: baseDate.addingTimeInterval(-620),
        updatedAt: baseDate,
        endedAt: nil,
        estimatedEndAt: baseDate.addingTimeInterval(240),
        exitCode: nil,
        safeLogTail: nil,
        sequence: 42
    )

    static let failedRun = RunSnapshot(
        id: UUID(uuidString: "018f0d8a-8c0a-7000-8000-000000000002")!,
        machineID: "machine_ci",
        machineName: "CI Builder",
        title: "Release build",
        source: "webhook",
        executionStatus: .failed,
        healthStatus: .offline,
        attentionStatus: .warning,
        progress: RunProgress(
            kind: .indeterminate,
            current: nil,
            total: nil,
            fraction: nil,
            unit: nil,
            source: "unknown"
        ),
        phase: "Signing",
        safeMessage: "Release build stopped during signing.",
        startedAt: baseDate.addingTimeInterval(-1_800),
        updatedAt: baseDate.addingTimeInterval(-900),
        endedAt: baseDate.addingTimeInterval(-900),
        estimatedEndAt: nil,
        exitCode: 65,
        safeLogTail: [
            "[redacted] signing identity was unavailable",
            "Build finished with exit code 65"
        ],
        sequence: 18
    )

    static let placeholderRun = RunSnapshot(
        id: UUID(),
        machineID: "placeholder",
        machineName: "Machine",
        title: "A run title appears here",
        executionStatus: .running,
        healthStatus: .healthy,
        attentionStatus: .none,
        progress: RunProgress(
            kind: .determinate,
            current: 40,
            total: 100,
            fraction: 0.4,
            unit: nil,
            source: "explicit"
        ),
        phase: "Working",
        safeMessage: nil,
        startedAt: baseDate,
        updatedAt: baseDate,
        endedAt: nil,
        estimatedEndAt: nil,
        exitCode: nil,
        safeLogTail: nil,
        sequence: 1
    )

    static let machine = MachineSnapshot(
        id: "machine_mac_studio",
        displayName: "Mac Studio",
        platform: "macOS",
        architecture: "arm64",
        cliVersion: "1.0.0",
        lastSeenAt: baseDate,
        pairedAt: baseDate.addingTimeInterval(-86_400),
        subscriptionID: "subscription_1",
        isSubscribed: true
    )

    static let message = RichMessage(
        id: "notification_1",
        machineID: machine.id,
        title: "Dataset ready",
        subtitle: "Training artifacts",
        body: "The sanitized dataset summary is available on Mac Studio.",
        level: "success",
        fields: [.init(name: "Rows", value: "12,840")],
        createdAt: baseDate,
        expiresAt: nil
    )

    static let events: [RunFeedEvent] = [
        RunFeedEvent(
            id: UUID(uuidString: "018f0d8a-8c0a-7000-8000-000000000010")!,
            sequence: 1,
            type: "run.started",
            occurredAt: activeRun.startedAt,
            phase: nil,
            message: "Run started",
            progress: nil
        ),
        RunFeedEvent(
            id: UUID(uuidString: "018f0d8a-8c0a-7000-8000-000000000011")!,
            sequence: 41,
            type: "run.progress",
            occurredAt: baseDate,
            phase: "Optimizing",
            message: "Processing item 72",
            progress: activeRun.progress
        )
    ]

    static let longEnglishDetail = RunDetail(
        run: RunSnapshot(
            id: activeRun.id,
            machineID: activeRun.machineID,
            machineName: "Mac Studio in the machine-learning laboratory",
            title: "Long-running constrained optimization experiment with a deliberately descriptive safe title",
            executionStatus: .running,
            healthStatus: .stale,
            attentionStatus: .information,
            progress: activeRun.progress,
            phase: "Evaluating the final group of candidate solutions without exposing source data",
            safeMessage: "The experiment is healthy. This deliberately long message verifies wrapping without revealing command arguments, directories, environment values, or full output.",
            startedAt: activeRun.startedAt,
            updatedAt: activeRun.updatedAt,
            endedAt: nil,
            estimatedEndAt: activeRun.estimatedEndAt,
            exitCode: nil,
            safeLogTail: nil,
            sequence: activeRun.sequence
        ),
        feed: events
    )

    static let longChineseDetail = RunDetail(
        run: RunSnapshot(
            id: failedRun.id,
            machineID: failedRun.machineID,
            machineName: "上海实验室的 Mac Studio 工作站",
            title: "用于验证超长简体中文标题换行和辅助功能字号的优化实验",
            executionStatus: .failed,
            healthStatus: .offline,
            attentionStatus: .actionRequired,
            progress: failedRun.progress,
            phase: "安全地汇总实验结果",
            safeMessage: "任务已结束。这是一段经过脱敏的安全摘要，不包含完整命令、目录、环境变量、源代码或完整输出。",
            startedAt: failedRun.startedAt,
            updatedAt: failedRun.updatedAt,
            endedAt: failedRun.endedAt,
            estimatedEndAt: nil,
            exitCode: failedRun.exitCode,
            safeLogTail: nil,
            sequence: failedRun.sequence
        ),
        feed: events
    )

    @MainActor
    static func store() -> RunBuoyStore {
        let snapshot = CachedSnapshot(
            runs: [activeRun, failedRun],
            machines: [machine],
            messages: [message],
            savedAt: baseDate
        )
        return RunBuoyStore(
            api: PreviewAPI(snapshot: snapshot, events: events),
            identityStore: PreviewIdentityStore(),
            cache: LocalCacheStore(
                fileURL: FileManager.default.temporaryDirectory
                    .appendingPathComponent("runbuoy-preview-cache.json")
            ),
            initialSnapshot: snapshot
        )
    }
}

private struct PreviewIdentityStore: DeviceIdentityStoring {
    func load() throws -> DeviceIdentity? {
        DeviceIdentity(deviceID: "preview-device", workspaceID: "preview-workspace", credential: "preview")
    }
    func save(_ identity: DeviceIdentity) throws {}
    func remove() throws {}
}

private struct PreviewAPI: RunBuoyAPI {
    let snapshot: CachedSnapshot
    let events: [RunFeedEvent]

    func bootstrap(installationID: String, appVersion: String, osVersion: String) async throws -> DeviceIdentity {
        DeviceIdentity(deviceID: "preview-device", workspaceID: "preview-workspace", credential: "preview")
    }
    func listRuns() async throws -> [RunSnapshot] { snapshot.runs }
    func runDetail(id: UUID) async throws -> RunDetail {
        RunDetail(run: snapshot.runs.first(where: { $0.id == id }) ?? snapshot.runs[0], feed: events)
    }
    func listMachines() async throws -> [MachineSnapshot] { snapshot.machines }
    func listMessages() async throws -> [RichMessage] { snapshot.messages }
    func claimPairing(_ code: PairingCode) async throws {}
    func registerNotificationToken(_ token: String) async throws {}
    func registerPushToStartToken(_ token: String) async throws {}
    func registerActivityToken(
        _ token: String,
        activityID: String,
        runID: String,
        generation: Int
    ) async throws {}
    func syncActivities(_ activities: [ActivityRegistration]) async throws {}
    func updatePreferences(_ preferences: DevicePreferences) async throws {}
    func deleteSubscription(_ id: String) async throws {}
}
