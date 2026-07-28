import Foundation

protocol ForwardCompatibleStatus: RawRepresentable, Codable, Hashable, Sendable
where RawValue == String {
    static var unknown: Self { get }
}

extension ForwardCompatibleStatus {
    init(from decoder: Decoder) throws {
        let value = try decoder.singleValueContainer().decode(String.self)
        self = Self(rawValue: value) ?? .unknown
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(rawValue)
    }
}

enum ExecutionStatus: String, CaseIterable, ForwardCompatibleStatus {
    case created = "CREATED"
    case starting = "STARTING"
    case running = "RUNNING"
    case succeeded = "SUCCEEDED"
    case failed = "FAILED"
    case cancelled = "CANCELLED"
    case lost = "LOST"
    case unknown = "UNKNOWN"

    var isActive: Bool {
        switch self {
        case .created, .starting, .running: true
        default: false
        }
    }
}

enum HealthStatus: String, CaseIterable, ForwardCompatibleStatus {
    case healthy = "HEALTHY"
    case stale = "STALE"
    case offline = "OFFLINE"
    case unknown = "UNKNOWN"
}

enum AttentionStatus: String, CaseIterable, ForwardCompatibleStatus {
    case none = "NONE"
    case information = "INFORMATION"
    case warning = "WARNING"
    case actionRequired = "ACTION_REQUIRED"
    case unknown = "UNKNOWN"
}

struct RunProgress: Codable, Hashable, Sendable {
    enum Kind: String, Codable, Sendable {
        case determinate
        case indeterminate
    }

    let kind: Kind
    let current: Double?
    let total: Double?
    let fraction: Double?
    let unit: String?
    let source: String
    let estimatedEndAt: Date?

    private enum CodingKeys: String, CodingKey {
        case kind
        case current
        case total
        case fraction
        case unit
        case source
        case estimatedEndAt = "estimated_end_at"
    }

    init(
        kind: Kind,
        current: Double?,
        total: Double?,
        fraction: Double?,
        unit: String?,
        source: String,
        estimatedEndAt: Date? = nil
    ) {
        self.kind = kind
        self.current = current
        self.total = total
        self.fraction = fraction
        self.unit = unit
        self.source = source
        self.estimatedEndAt = estimatedEndAt
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        let rawKind = try values.decodeIfPresent(String.self, forKey: .kind)
        kind = Kind(rawValue: rawKind ?? "") ?? .indeterminate
        current = try values.decodeIfPresent(Double.self, forKey: .current)
        total = try values.decodeIfPresent(Double.self, forKey: .total)
        fraction = try values.decodeIfPresent(Double.self, forKey: .fraction)
        unit = try values.decodeIfPresent(String.self, forKey: .unit)
        source = try values.decodeIfPresent(String.self, forKey: .source) ?? "unknown"
        estimatedEndAt = try values.decodeIfPresent(Date.self, forKey: .estimatedEndAt)
    }

    func encode(to encoder: Encoder) throws {
        var values = encoder.container(keyedBy: CodingKeys.self)
        try values.encode(kind, forKey: .kind)
        try values.encodeIfPresent(current, forKey: .current)
        try values.encodeIfPresent(total, forKey: .total)
        try values.encodeIfPresent(fraction, forKey: .fraction)
        try values.encodeIfPresent(unit, forKey: .unit)
        try values.encode(source, forKey: .source)
        try values.encodeIfPresent(estimatedEndAt, forKey: .estimatedEndAt)
    }

    var boundedFraction: Double? {
        guard kind == .determinate, let fraction else { return nil }
        return min(max(fraction, 0), 1)
    }
}

struct RunSnapshot: Codable, Identifiable, Hashable, Sendable {
    let id: UUID
    let machineID: String
    let machineName: String
    let title: String
    let source: String?
    let executionStatus: ExecutionStatus
    let healthStatus: HealthStatus
    let attentionStatus: AttentionStatus
    let progress: RunProgress?
    let phase: String?
    let safeMessage: String?
    let startedAt: Date
    let updatedAt: Date
    let endedAt: Date?
    let estimatedEndAt: Date?
    let exitCode: Int?
    let safeLogTail: [String]?
    let sequence: Int

    private enum CodingKeys: String, CodingKey {
        case id
        case machineID = "machine_id"
        case machineName = "machine_name"
        case title
        case source
        case executionStatus = "execution_status"
        case healthStatus = "health_status"
        case attentionStatus = "attention_status"
        case progress
        case phase
        case safeMessage = "safe_message"
        case startedAt = "started_at"
        case updatedAt = "updated_at"
        case endedAt = "ended_at"
        case estimatedEndAt = "estimated_end_at"
        case exitCode = "exit_code"
        case safeLogTail = "safe_log_tail"
        case sequence
        case seq
        case lastSeq = "last_seq"
    }

    init(
        id: UUID,
        machineID: String,
        machineName: String,
        title: String,
        source: String? = nil,
        executionStatus: ExecutionStatus,
        healthStatus: HealthStatus,
        attentionStatus: AttentionStatus,
        progress: RunProgress?,
        phase: String?,
        safeMessage: String?,
        startedAt: Date,
        updatedAt: Date,
        endedAt: Date?,
        estimatedEndAt: Date?,
        exitCode: Int?,
        safeLogTail: [String]?,
        sequence: Int
    ) {
        self.id = id
        self.machineID = machineID
        self.machineName = machineName
        self.title = title
        self.source = source
        self.executionStatus = executionStatus
        self.healthStatus = healthStatus
        self.attentionStatus = attentionStatus
        self.progress = progress
        self.phase = phase
        self.safeMessage = safeMessage
        self.startedAt = startedAt
        self.updatedAt = updatedAt
        self.endedAt = endedAt
        self.estimatedEndAt = estimatedEndAt
        self.exitCode = exitCode
        self.safeLogTail = safeLogTail
        self.sequence = sequence
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decode(UUID.self, forKey: .id)
        machineID = try values.decode(String.self, forKey: .machineID)
        machineName = try values.decodeIfPresent(String.self, forKey: .machineName) ?? machineID
        title = try values.decode(String.self, forKey: .title)
        source = try values.decodeIfPresent(String.self, forKey: .source)
        executionStatus = try values.decode(ExecutionStatus.self, forKey: .executionStatus)
        healthStatus = try values.decode(HealthStatus.self, forKey: .healthStatus)
        attentionStatus = try values.decode(AttentionStatus.self, forKey: .attentionStatus)
        progress = try values.decodeIfPresent(RunProgress.self, forKey: .progress)
        phase = try values.decodeIfPresent(String.self, forKey: .phase)
        safeMessage = try values.decodeIfPresent(String.self, forKey: .safeMessage)
        updatedAt = try values.decode(Date.self, forKey: .updatedAt)
        startedAt = try values.decodeIfPresent(Date.self, forKey: .startedAt) ?? updatedAt
        endedAt = try values.decodeIfPresent(Date.self, forKey: .endedAt)
        estimatedEndAt = try values.decodeIfPresent(Date.self, forKey: .estimatedEndAt)
            ?? progress?.estimatedEndAt
        exitCode = try values.decodeIfPresent(Int.self, forKey: .exitCode)
        safeLogTail = try values.decodeIfPresent([String].self, forKey: .safeLogTail)
        sequence = try values.decodeIfPresent(Int.self, forKey: .sequence)
            ?? values.decodeIfPresent(Int.self, forKey: .seq)
            ?? values.decodeIfPresent(Int.self, forKey: .lastSeq)
            ?? 0
    }

    func encode(to encoder: Encoder) throws {
        var values = encoder.container(keyedBy: CodingKeys.self)
        try values.encode(id, forKey: .id)
        try values.encode(machineID, forKey: .machineID)
        try values.encode(machineName, forKey: .machineName)
        try values.encode(title, forKey: .title)
        try values.encodeIfPresent(source, forKey: .source)
        try values.encode(executionStatus, forKey: .executionStatus)
        try values.encode(healthStatus, forKey: .healthStatus)
        try values.encode(attentionStatus, forKey: .attentionStatus)
        try values.encodeIfPresent(progress, forKey: .progress)
        try values.encodeIfPresent(phase, forKey: .phase)
        try values.encodeIfPresent(safeMessage, forKey: .safeMessage)
        try values.encode(startedAt, forKey: .startedAt)
        try values.encode(updatedAt, forKey: .updatedAt)
        try values.encodeIfPresent(endedAt, forKey: .endedAt)
        try values.encodeIfPresent(estimatedEndAt, forKey: .estimatedEndAt)
        try values.encodeIfPresent(exitCode, forKey: .exitCode)
        try values.encodeIfPresent(safeLogTail, forKey: .safeLogTail)
        try values.encode(sequence, forKey: .sequence)
    }
}

struct RunFeedEvent: Codable, Identifiable, Hashable, Sendable {
    let id: UUID
    let sequence: Int
    let type: String
    let occurredAt: Date
    let phase: String?
    let message: String?
    let progress: RunProgress?

    private enum CodingKeys: String, CodingKey {
        case id = "event_id"
        case sequence = "seq"
        case type
        case occurredAt = "occurred_at"
        case phase
        case message
        case progress
        case payload
    }

    private enum PayloadKeys: String, CodingKey {
        case phase
        case message
        case progress
    }

    init(
        id: UUID,
        sequence: Int,
        type: String,
        occurredAt: Date,
        phase: String?,
        message: String?,
        progress: RunProgress?
    ) {
        self.id = id
        self.sequence = sequence
        self.type = type
        self.occurredAt = occurredAt
        self.phase = phase
        self.message = message
        self.progress = progress
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decode(UUID.self, forKey: .id)
        sequence = try values.decode(Int.self, forKey: .sequence)
        type = try values.decode(String.self, forKey: .type)
        occurredAt = try values.decode(Date.self, forKey: .occurredAt)
        if values.contains(.payload) {
            let payload = try values.nestedContainer(keyedBy: PayloadKeys.self, forKey: .payload)
            phase = try payload.decodeIfPresent(String.self, forKey: .phase)
            message = try payload.decodeIfPresent(String.self, forKey: .message)
            progress = try payload.decodeIfPresent(RunProgress.self, forKey: .progress)
        } else {
            phase = try values.decodeIfPresent(String.self, forKey: .phase)
            message = try values.decodeIfPresent(String.self, forKey: .message)
            progress = try values.decodeIfPresent(RunProgress.self, forKey: .progress)
        }
    }

    func encode(to encoder: Encoder) throws {
        var values = encoder.container(keyedBy: CodingKeys.self)
        try values.encode(id, forKey: .id)
        try values.encode(sequence, forKey: .sequence)
        try values.encode(type, forKey: .type)
        try values.encode(occurredAt, forKey: .occurredAt)
        var payload = values.nestedContainer(keyedBy: PayloadKeys.self, forKey: .payload)
        try payload.encodeIfPresent(phase, forKey: .phase)
        try payload.encodeIfPresent(message, forKey: .message)
        try payload.encodeIfPresent(progress, forKey: .progress)
    }
}

struct RunDetail: Codable, Sendable {
    let run: RunSnapshot
    let feed: [RunFeedEvent]

    private enum CodingKeys: String, CodingKey {
        case run
        case feed
        case events
    }

    init(run: RunSnapshot, feed: [RunFeedEvent]) {
        self.run = run
        self.feed = feed
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        run = try values.decode(RunSnapshot.self, forKey: .run)
        feed = try values.decodeIfPresent([RunFeedEvent].self, forKey: .feed)
            ?? values.decodeIfPresent([RunFeedEvent].self, forKey: .events)
            ?? []
    }

    func encode(to encoder: Encoder) throws {
        var values = encoder.container(keyedBy: CodingKeys.self)
        try values.encode(run, forKey: .run)
        try values.encode(feed, forKey: .feed)
    }
}

struct MachineSnapshot: Codable, Identifiable, Hashable, Sendable {
    let id: String
    let displayName: String
    let platform: String
    let architecture: String?
    let cliVersion: String
    let lastSeenAt: Date
    let pairedAt: Date
    let subscriptionID: String?
    let isSubscribed: Bool

    private enum CodingKeys: String, CodingKey {
        case id
        case displayName = "display_name"
        case platform
        case architecture
        case cliVersion = "cli_version"
        case lastSeenAt = "last_seen_at"
        case pairedAt = "paired_at"
        case subscriptionID = "subscription_id"
        case isSubscribed = "is_subscribed"
    }

    init(
        id: String,
        displayName: String,
        platform: String,
        architecture: String?,
        cliVersion: String,
        lastSeenAt: Date,
        pairedAt: Date,
        subscriptionID: String?,
        isSubscribed: Bool
    ) {
        self.id = id
        self.displayName = displayName
        self.platform = platform
        self.architecture = architecture
        self.cliVersion = cliVersion
        self.lastSeenAt = lastSeenAt
        self.pairedAt = pairedAt
        self.subscriptionID = subscriptionID
        self.isSubscribed = isSubscribed
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        id = try values.decode(String.self, forKey: .id)
        displayName = try values.decodeIfPresent(String.self, forKey: .displayName) ?? id
        platform = try values.decodeIfPresent(String.self, forKey: .platform) ?? String(localized: "status.unknown")
        architecture = try values.decodeIfPresent(String.self, forKey: .architecture)
        cliVersion = try values.decodeIfPresent(String.self, forKey: .cliVersion) ?? "—"
        lastSeenAt = try values.decodeIfPresent(Date.self, forKey: .lastSeenAt) ?? .distantPast
        pairedAt = try values.decodeIfPresent(Date.self, forKey: .pairedAt) ?? .distantPast
        subscriptionID = try values.decodeIfPresent(String.self, forKey: .subscriptionID)
        isSubscribed = try values.decodeIfPresent(Bool.self, forKey: .isSubscribed)
            ?? (subscriptionID != nil)
    }
}

enum MachineLocalLabel {
    static func key(for machineID: String) -> String {
        "runbuoy.machine-label.\(machineID)"
    }

    static func displayName(
        machineID: String,
        serverName: String,
        userDefaults: UserDefaults = .standard
    ) -> String {
        userDefaults.string(forKey: key(for: machineID)) ?? serverName
    }
}

enum MachineIcon: String, CaseIterable, Identifiable {
    case desktopcomputer
    case macProServer = "macpro.gen3.server"
    case macbook
    case macMini = "macmini"
    case macStudio = "macstudio"
    case macPro = "macpro.gen2"

    static let defaultValue = MachineIcon.desktopcomputer

    var id: String { rawValue }

    static func key(for machineID: String) -> String {
        "runbuoy.machine-icon.\(machineID)"
    }

    static func selected(
        for machineID: String,
        userDefaults: UserDefaults = .standard
    ) -> MachineIcon {
        guard let rawValue = userDefaults.string(forKey: key(for: machineID)),
              let icon = MachineIcon(rawValue: rawValue)
        else {
            return defaultValue
        }
        return icon
    }
}

struct RichMessage: Codable, Identifiable, Hashable, Sendable {
    struct Field: Codable, Identifiable, Hashable, Sendable {
        let name: String
        let value: String
        var id: String { "\(name):\(value)" }

        private enum CodingKeys: String, CodingKey {
            case name
            case label
            case value
        }

        init(name: String, value: String) {
            self.name = name
            self.value = value
        }

        init(from decoder: Decoder) throws {
            let values = try decoder.container(keyedBy: CodingKeys.self)
            name = try values.decodeIfPresent(String.self, forKey: .name)
                ?? values.decode(String.self, forKey: .label)
            value = try values.decode(String.self, forKey: .value)
        }

        func encode(to encoder: Encoder) throws {
            var values = encoder.container(keyedBy: CodingKeys.self)
            try values.encode(name, forKey: .name)
            try values.encode(value, forKey: .value)
        }
    }

    let id: String
    let machineID: String?
    let title: String
    let subtitle: String?
    let body: String
    let level: String
    let fields: [Field]
    let createdAt: Date
    let expiresAt: Date?

    private enum CodingKeys: String, CodingKey {
        case id
        case machineID = "machine_id"
        case title
        case subtitle
        case body
        case level
        case fields
        case createdAt = "created_at"
        case expiresAt = "expires_at"
    }

    init(
        id: String,
        machineID: String?,
        title: String,
        subtitle: String?,
        body: String,
        level: String,
        fields: [Field],
        createdAt: Date,
        expiresAt: Date?
    ) {
        self.id = id
        self.machineID = machineID
        self.title = title
        self.subtitle = subtitle
        self.body = body
        self.level = level
        self.fields = fields
        self.createdAt = createdAt
        self.expiresAt = expiresAt
    }
}

struct DeviceIdentity: Codable, Equatable, Sendable {
    let deviceID: String
    let workspaceID: String
    let credential: String

    private enum CodingKeys: String, CodingKey {
        case deviceID = "device_id"
        case workspaceID = "workspace_id"
        case credential
        case token
    }

    init(deviceID: String, workspaceID: String, credential: String) {
        self.deviceID = deviceID
        self.workspaceID = workspaceID
        self.credential = credential
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        deviceID = try values.decode(String.self, forKey: .deviceID)
        workspaceID = try values.decode(String.self, forKey: .workspaceID)
        credential = try values.decodeIfPresent(String.self, forKey: .credential)
            ?? values.decode(String.self, forKey: .token)
    }

    func encode(to encoder: Encoder) throws {
        var values = encoder.container(keyedBy: CodingKeys.self)
        try values.encode(deviceID, forKey: .deviceID)
        try values.encode(workspaceID, forKey: .workspaceID)
        try values.encode(credential, forKey: .credential)
    }
}

struct PairingCode: Equatable, Sendable {
    let sessionID: String
    let challenge: String
    let machineDisplayName: String
    let platform: String?

    static func decode(_ value: String) throws -> PairingCode {
        if let data = value.data(using: .utf8),
           let payload = try? JSONDecoder().decode(Payload.self, from: data) {
            return payload.code
        }

        guard let components = URLComponents(string: value),
              components.scheme?.lowercased() == "runbuoy",
              components.host?.lowercased() == "pair",
              let sessionID = components.path.split(separator: "/").first.map(String.init)
                ?? components.queryItems?.first(where: { $0.name == "session" })?.value
                ?? components.queryItems?.first(where: { $0.name == "session_id" })?.value,
              let challenge = components.queryItems?.first(where: { $0.name == "challenge" })?.value,
              let machineName = components.queryItems?.first(where: { $0.name == "machine" })?.value
        else {
            throw PairingCodeError.invalidCode
        }

        return PairingCode(
            sessionID: sessionID,
            challenge: challenge,
            machineDisplayName: machineName,
            platform: components.queryItems?.first(where: { $0.name == "platform" })?.value
        )
    }

    private struct Payload: Decodable {
        let sessionID: String
        let challenge: String
        let machineDisplayName: String
        let platform: String?

        private enum CodingKeys: String, CodingKey {
            case sessionID = "pairing_session_id"
            case challenge
            case machineDisplayName = "machine_display_name"
            case machine
            case platform
        }

        init(from decoder: Decoder) throws {
            let values = try decoder.container(keyedBy: CodingKeys.self)
            sessionID = try values.decode(String.self, forKey: .sessionID)
            challenge = try values.decode(String.self, forKey: .challenge)
            machineDisplayName = try values.decodeIfPresent(String.self, forKey: .machineDisplayName)
                ?? values.decode(String.self, forKey: .machine)
            platform = try values.decodeIfPresent(String.self, forKey: .platform)
        }

        var code: PairingCode {
            PairingCode(
                sessionID: sessionID,
                challenge: challenge,
                machineDisplayName: machineDisplayName,
                platform: platform
            )
        }
    }
}

enum PairingCodeError: LocalizedError {
    case invalidCode

    var errorDescription: String? {
        String(localized: "pairing.invalid_code")
    }
}
