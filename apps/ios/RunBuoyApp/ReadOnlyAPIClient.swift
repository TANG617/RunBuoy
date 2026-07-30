import Foundation

enum DeviceAPIEndpoint: Equatable, Sendable {
    case bootstrap
    case runs
    case run(UUID)
    case machines
    case messages
    case resolvePairingCode
    case claimPairing(String)
    case notificationToken(String)
    case pushToStartToken(String)
    case activityToken(String)
    case activitySync(String)
    case preferences
    case subscription(String)

    var method: String {
        switch self {
        case .runs, .run, .machines, .messages:
            "GET"
        case .notificationToken, .pushToStartToken, .activityToken:
            "PUT"
        case .preferences:
            "PATCH"
        case .subscription:
            "DELETE"
        case .bootstrap, .resolvePairingCode, .claimPairing, .activitySync:
            "POST"
        }
    }

    var path: String {
        switch self {
        case .bootstrap: "/v1/devices/bootstrap"
        case .runs: "/v1/runs"
        case .run(let id): "/v1/runs/\(id.uuidString.lowercased())"
        case .machines: "/v1/machines"
        case .messages: "/v1/notifications"
        case .resolvePairingCode: "/v1/pairing-sessions/resolve"
        case .claimPairing(let id): "/v1/pairing-sessions/\(id.pathComponent)/claim"
        case .notificationToken(let id): "/v1/devices/\(id.pathComponent)/notification-token"
        case .pushToStartToken(let id): "/v1/devices/\(id.pathComponent)/push-to-start-token"
        case .activityToken(let id): "/v1/live-activities/\(id.pathComponent)/update-token"
        case .activitySync(let id): "/v1/devices/\(id.pathComponent)/activity-sync"
        case .preferences: "/v1/device-preferences"
        case .subscription(let id): "/v1/machine-subscriptions/\(id.pathComponent)"
        }
    }
}

private extension String {
    var pathComponent: String {
        addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/")))
            ?? self
    }
}

protocol RunBuoyAPI: Sendable {
    func bootstrap(installationID: String, appVersion: String, osVersion: String) async throws -> DeviceIdentity
    func listRuns() async throws -> [RunSnapshot]
    func runDetail(id: UUID) async throws -> RunDetail
    func listMachines() async throws -> [MachineSnapshot]
    func listMessages() async throws -> [RichMessage]
    func resolvePairingCode(_ shortCode: String) async throws -> PairingCode
    func claimPairing(_ code: PairingCode) async throws
    func registerNotificationToken(_ token: String) async throws
    func registerPushToStartToken(_ token: String) async throws
    func registerActivityToken(
        _ token: String,
        activityID: String,
        runID: String,
        generation: Int
    ) async throws
    func syncActivities(_ activities: [ActivityRegistration]) async throws
    func updatePreferences(_ preferences: DevicePreferences) async throws
    func deleteSubscription(_ id: String) async throws
}

struct DevicePreferences: Codable, Equatable, Sendable {
    let notificationsEnabled: Bool
    let liveActivitiesEnabled: Bool
    let showSafeMessages: Bool

    private enum CodingKeys: String, CodingKey {
        case liveActivitiesEnabled = "live_activities_enabled"
        case failureNotificationsEnabled = "failure_notifications_enabled"
        case successNotificationsEnabled = "success_notifications_enabled"
    }

    func encode(to encoder: Encoder) throws {
        var values = encoder.container(keyedBy: CodingKeys.self)
        try values.encode(liveActivitiesEnabled, forKey: .liveActivitiesEnabled)
        try values.encode(notificationsEnabled, forKey: .failureNotificationsEnabled)
        try values.encode(notificationsEnabled, forKey: .successNotificationsEnabled)
    }

    init(notificationsEnabled: Bool, liveActivitiesEnabled: Bool, showSafeMessages: Bool) {
        self.notificationsEnabled = notificationsEnabled
        self.liveActivitiesEnabled = liveActivitiesEnabled
        self.showSafeMessages = showSafeMessages
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        liveActivitiesEnabled = try values.decodeIfPresent(Bool.self, forKey: .liveActivitiesEnabled) ?? true
        let failure = try values.decodeIfPresent(Bool.self, forKey: .failureNotificationsEnabled) ?? true
        let success = try values.decodeIfPresent(Bool.self, forKey: .successNotificationsEnabled) ?? true
        notificationsEnabled = failure || success
        showSafeMessages = true
    }
}

struct ActivityRegistration: Codable, Equatable, Sendable {
    let activityID: String
    let runID: String
    let updateToken: String?
    let tokenGeneration: Int
    let state: String
    let lastSequence: Int

    private enum CodingKeys: String, CodingKey {
        case activityID = "activity_id"
        case runID = "run_id"
        case updateToken = "update_token"
        case tokenGeneration = "token_generation"
        case state
        case lastSequence = "last_sequence"
    }

    init(
        activityID: String,
        runID: String,
        updateToken: String? = nil,
        tokenGeneration: Int = 1,
        state: String,
        lastSequence: Int = 0
    ) {
        self.activityID = activityID
        self.runID = runID
        self.updateToken = updateToken
        self.tokenGeneration = tokenGeneration
        self.state = state
        self.lastSequence = lastSequence
    }
}

struct URLSessionRunBuoyAPI: RunBuoyAPI, @unchecked Sendable {
    private let baseURLProvider: @Sendable () -> URL
    private let session: URLSession
    private let identityStore: any DeviceIdentityStoring

    init(
        baseURL: URL,
        session: URLSession = .shared,
        identityStore: any DeviceIdentityStoring
    ) {
        baseURLProvider = { baseURL }
        self.session = session
        self.identityStore = identityStore
    }

    init(
        baseURLProvider: @escaping @Sendable () -> URL,
        session: URLSession = .shared,
        identityStore: any DeviceIdentityStoring
    ) {
        self.baseURLProvider = baseURLProvider
        self.session = session
        self.identityStore = identityStore
    }

    func bootstrap(installationID: String, appVersion: String, osVersion: String) async throws -> DeviceIdentity {
        let body = BootstrapBody(
            installationID: installationID,
            appVersion: appVersion,
            osVersion: osVersion
        )
        return try await request(.bootstrap, body: body, authenticated: false)
    }

    func listRuns() async throws -> [RunSnapshot] {
        try await requestList(.runs, key: "runs")
    }

    func runDetail(id: UUID) async throws -> RunDetail {
        let data = try await requestData(.run(id), body: Optional<EmptyBody>.none, authenticated: true)
        if let detail = try? JSONDecoder.runBuoy.decode(RunDetail.self, from: data) {
            return RunDetail(run: detail.run, feed: detail.feed.sorted { $0.sequence < $1.sequence })
        }
        let envelope = try JSONDecoder.runBuoy.decode(RunDetailEnvelope.self, from: data)
        return RunDetail(run: envelope.run, feed: envelope.events.sorted { $0.sequence < $1.sequence })
    }

    func listMachines() async throws -> [MachineSnapshot] {
        try await requestList(.machines, key: "machines")
    }

    func listMessages() async throws -> [RichMessage] {
        try await requestList(.messages, key: "notifications")
    }

    func resolvePairingCode(_ shortCode: String) async throws -> PairingCode {
        let response: ResolvedPairingCode = try await request(
            .resolvePairingCode,
            body: ResolvePairingCodeBody(shortCode: shortCode)
        )
        return response.code
    }

    func claimPairing(_ code: PairingCode) async throws {
        let body = ClaimBody(challenge: code.challenge)
        try await requestWithoutResponse(.claimPairing(code.sessionID), body: body)
    }

    func registerNotificationToken(_ token: String) async throws {
        let identity = try requireIdentity()
        try await requestWithoutResponse(
            .notificationToken(identity.deviceID),
            body: TokenBody(token: token)
        )
    }

    func registerPushToStartToken(_ token: String) async throws {
        let identity = try requireIdentity()
        try await requestWithoutResponse(
            .pushToStartToken(identity.deviceID),
            body: TokenBody(token: token)
        )
    }

    func registerActivityToken(
        _ token: String,
        activityID: String,
        runID: String,
        generation: Int
    ) async throws {
        let identity = try requireIdentity()
        try await requestWithoutResponse(
            .activityToken(activityID),
            body: ActivityTokenBody(
                token: token,
                deviceID: identity.deviceID,
                runID: runID,
                generation: generation
            )
        )
    }

    func syncActivities(_ activities: [ActivityRegistration]) async throws {
        let identity = try requireIdentity()
        try await requestWithoutResponse(
            .activitySync(identity.deviceID),
            body: ActivitySyncBody(activities: activities)
        )
    }

    func updatePreferences(_ preferences: DevicePreferences) async throws {
        try await requestWithoutResponse(.preferences, body: preferences)
    }

    func deleteSubscription(_ id: String) async throws {
        try await requestWithoutResponse(.subscription(id), body: Optional<EmptyBody>.none)
    }

    private func request<Response: Decodable, Body: Encodable>(
        _ endpoint: DeviceAPIEndpoint,
        body: Body?,
        authenticated: Bool = true
    ) async throws -> Response {
        let data = try await requestData(endpoint, body: body, authenticated: authenticated)
        return try JSONDecoder.runBuoy.decode(Response.self, from: data)
    }

    private func requestList<Element: Decodable>(
        _ endpoint: DeviceAPIEndpoint,
        key: String
    ) async throws -> [Element] {
        let data = try await requestData(endpoint, body: Optional<EmptyBody>.none, authenticated: true)
        if let direct = try? JSONDecoder.runBuoy.decode([Element].self, from: data) {
            return direct
        }
        return try JSONDecoder.runBuoy.decode(ListEnvelope<Element>.self, from: data).values(for: key)
    }

    private func requestWithoutResponse<Body: Encodable>(
        _ endpoint: DeviceAPIEndpoint,
        body: Body?
    ) async throws {
        _ = try await requestData(endpoint, body: body, authenticated: true)
    }

    private func requestData<Body: Encodable>(
        _ endpoint: DeviceAPIEndpoint,
        body: Body?,
        authenticated: Bool
    ) async throws -> Data {
        let baseURL = baseURLProvider()
        guard let url = URL(string: endpoint.path, relativeTo: baseURL)?.absoluteURL else {
            throw APIError.invalidURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = endpoint.method
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            request.httpBody = try JSONEncoder.runBuoy.encode(body)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        if authenticated {
            request.setValue("Bearer \(try requireIdentity().credential)", forHTTPHeaderField: "Authorization")
        }

        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        guard 200..<300 ~= response.statusCode else {
            throw APIError.httpStatus(response.statusCode)
        }
        return data
    }

    private func requireIdentity() throws -> DeviceIdentity {
        guard let identity = try identityStore.load() else {
            throw APIError.missingIdentity
        }
        return identity
    }

    private struct BootstrapBody: Encodable {
        let installationID: String
        let appVersion: String
        let osVersion: String

        private enum CodingKeys: String, CodingKey {
            case installationID = "installation_id"
            case appVersion = "app_version"
            case osVersion = "os_version"
        }
    }

    private struct TokenBody: Encodable {
        let token: String
    }

    private struct ClaimBody: Encodable {
        let challenge: String
    }

    private struct ResolvePairingCodeBody: Encodable {
        let shortCode: String

        private enum CodingKeys: String, CodingKey {
            case shortCode = "short_code"
        }
    }

    private struct ActivityTokenBody: Encodable {
        let token: String
        let deviceID: String
        let runID: String
        let generation: Int

        private enum CodingKeys: String, CodingKey {
            case token
            case deviceID = "device_id"
            case runID = "run_id"
            case generation
        }
    }

    private struct ActivitySyncBody: Encodable {
        let activities: [ActivityRegistration]
    }

    private struct EmptyBody: Encodable {}
}

private struct ResolvedPairingCode: Decodable {
    let sessionID: String
    let challenge: String
    let machineDisplayName: String
    let platform: String?

    private enum CodingKeys: String, CodingKey {
        case sessionID = "pairing_session_id"
        case challenge
        case machineDisplayName = "machine_display_name"
        case platform
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

private struct RunDetailEnvelope: Decodable {
    let run: RunSnapshot
    let events: [RunFeedEvent]

    private enum CodingKeys: String, CodingKey {
        case run
        case events
        case feed
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        run = try values.decode(RunSnapshot.self, forKey: .run)
        events = try values.decodeIfPresent([RunFeedEvent].self, forKey: .events)
            ?? values.decodeIfPresent([RunFeedEvent].self, forKey: .feed)
            ?? []
    }
}

private struct ListEnvelope<Element: Decodable>: Decodable {
    let valuesByKey: [String: [Element]]

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: DynamicCodingKey.self)
        var result: [String: [Element]] = [:]
        for key in values.allKeys {
            if let items = try? values.decode([Element].self, forKey: key) {
                result[key.stringValue] = items
            }
        }
        valuesByKey = result
    }

    func values(for key: String) throws -> [Element] {
        guard let values = valuesByKey[key] ?? valuesByKey["items"] else {
            throw APIError.invalidResponse
        }
        return values
    }
}

private struct DynamicCodingKey: CodingKey {
    let stringValue: String
    let intValue: Int? = nil

    init?(stringValue: String) {
        self.stringValue = stringValue
    }

    init?(intValue: Int) {
        return nil
    }
}

enum APIError: LocalizedError, Equatable {
    case invalidURL
    case invalidResponse
    case httpStatus(Int)
    case missingIdentity

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            String(localized: "error.invalid_url")
        case .invalidResponse:
            String(localized: "error.invalid_response")
        case .httpStatus(let status):
            String(format: String(localized: "error.http_status"), status)
        case .missingIdentity:
            String(localized: "error.missing_identity")
        }
    }
}
