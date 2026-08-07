import Foundation

enum DeviceAPIEndpoint: Equatable, Sendable {
    case bootstrap
    case runs
    case run(UUID)
    case machines
    case messages
    case sync
    case historyRuns
    case historyMessages
    case claimPairing(String)
    case notificationToken(String)
    case pushToStartToken(String)
    case activityToken(String)
    case activitySync(String)
    case preferences
    case subscription(String)

    var method: String {
        switch self {
        case .runs, .run, .machines, .messages, .sync, .historyRuns, .historyMessages:
            "GET"
        case .notificationToken, .pushToStartToken, .activityToken:
            "PUT"
        case .preferences:
            "PATCH"
        case .subscription:
            "DELETE"
        case .bootstrap, .claimPairing, .activitySync:
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
        case .sync: "/v1/sync"
        case .historyRuns: "/v1/history/runs"
        case .historyMessages: "/v1/history/notifications"
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
    func sync(cursor: Int?) async throws -> SyncResult
    func historyRuns(cursor: String?, limit: Int, machineID: String?) async throws -> HistoryPage<RunSnapshot>
    func historyMessages(cursor: String?, limit: Int, machineID: String?) async throws -> HistoryPage<RichMessage>
    func claimPairing(_ code: PairingCode) async throws
    func registerNotificationToken(_ token: String) async throws
    func registerPushToStartToken(_ token: String, generation: Int) async throws
    func registerActivityToken(
        _ token: String,
        activityID: String,
        runID: String,
        generation: Int
    ) async throws
    func syncActivities(
        _ activities: [ActivityRegistration],
        frequentPushesEnabled: Bool
    ) async throws
    func updatePreferences(_ preferences: DevicePreferences) async throws
    func deleteSubscription(_ id: String) async throws
}

struct SyncSnapshot: Decodable, Equatable, Sendable {
    let schemaVersion: Int
    let nextCursor: Int
    let serverTime: Date
    let runs: [RunSnapshot]
    let machines: [MachineSnapshot]
    let notifications: [RichMessage]
    let historyRunsNextCursor: String?
    let historyRunsHasMore: Bool
    let historyNotificationsNextCursor: String?
    let historyNotificationsHasMore: Bool

    private enum CodingKeys: String, CodingKey {
        case schemaVersion = "schema_version"
        case nextCursor = "next_cursor"
        case serverTime = "server_time"
        case runs
        case machines
        case notifications
        case historyRunsNextCursor = "history_runs_next_cursor"
        case historyRunsHasMore = "history_runs_has_more"
        case historyNotificationsNextCursor = "history_notifications_next_cursor"
        case historyNotificationsHasMore = "history_notifications_has_more"
    }

    init(
        schemaVersion: Int = 1,
        nextCursor: Int,
        serverTime: Date,
        runs: [RunSnapshot],
        machines: [MachineSnapshot],
        notifications: [RichMessage],
        historyRunsNextCursor: String? = nil,
        historyRunsHasMore: Bool = false,
        historyNotificationsNextCursor: String? = nil,
        historyNotificationsHasMore: Bool = false
    ) {
        self.schemaVersion = schemaVersion
        self.nextCursor = nextCursor
        self.serverTime = serverTime
        self.runs = runs
        self.machines = machines
        self.notifications = notifications
        self.historyRunsNextCursor = historyRunsNextCursor
        self.historyRunsHasMore = historyRunsHasMore
        self.historyNotificationsNextCursor = historyNotificationsNextCursor
        self.historyNotificationsHasMore = historyNotificationsHasMore
    }

    init(from decoder: Decoder) throws {
        let values = try decoder.container(keyedBy: CodingKeys.self)
        schemaVersion = try values.decode(Int.self, forKey: .schemaVersion)
        nextCursor = try values.decode(Int.self, forKey: .nextCursor)
        serverTime = try values.decode(Date.self, forKey: .serverTime)
        runs = try values.decode([RunSnapshot].self, forKey: .runs)
        machines = try values.decode([MachineSnapshot].self, forKey: .machines)
        notifications = try values.decode([RichMessage].self, forKey: .notifications)
        historyRunsNextCursor = try values.decodeIfPresent(String.self, forKey: .historyRunsNextCursor)
        historyRunsHasMore = try values.decodeIfPresent(Bool.self, forKey: .historyRunsHasMore)
            ?? (historyRunsNextCursor != nil)
        historyNotificationsNextCursor = try values.decodeIfPresent(
            String.self,
            forKey: .historyNotificationsNextCursor
        )
        historyNotificationsHasMore = try values.decodeIfPresent(
            Bool.self,
            forKey: .historyNotificationsHasMore
        ) ?? (historyNotificationsNextCursor != nil)
    }
}

enum SyncResult: Equatable, Sendable {
    case notModified
    case snapshot(SyncSnapshot)
}

struct HistoryPage<Element: Decodable & Sendable>: Decodable, Sendable {
    let items: [Element]
    let nextCursor: String?
    let hasMore: Bool

    private enum CodingKeys: String, CodingKey {
        case items
        case nextCursor = "next_cursor"
        case hasMore = "has_more"
    }
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

    func sync(cursor: Int?) async throws -> SyncResult {
        let identity = try requireIdentity()
        let queryItems = cursor.map { [URLQueryItem(name: "cursor", value: String($0))] } ?? []
        let headers = cursor.map {
            ["If-None-Match": "\"sync-\(identity.workspaceID)-\($0)\""]
        } ?? [:]
        let (data, response) = try await performRequest(
            .sync,
            body: Optional<EmptyBody>.none,
            authenticated: true,
            queryItems: queryItems,
            headers: headers
        )
        if response.statusCode == 304 {
            return .notModified
        }
        guard 200..<300 ~= response.statusCode else {
            throw APIError.httpStatus(response.statusCode)
        }
        return .snapshot(try JSONDecoder.runBuoy.decode(SyncSnapshot.self, from: data))
    }

    func historyRuns(
        cursor: String?,
        limit: Int,
        machineID: String?
    ) async throws -> HistoryPage<RunSnapshot> {
        try await historyPage(.historyRuns, cursor: cursor, limit: limit, machineID: machineID)
    }

    func historyMessages(
        cursor: String?,
        limit: Int,
        machineID: String?
    ) async throws -> HistoryPage<RichMessage> {
        try await historyPage(.historyMessages, cursor: cursor, limit: limit, machineID: machineID)
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

    func registerPushToStartToken(_ token: String, generation: Int) async throws {
        let identity = try requireIdentity()
        try await requestWithoutResponse(
            .pushToStartToken(identity.deviceID),
            body: TokenBody(token: token, generation: generation)
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

    func syncActivities(
        _ activities: [ActivityRegistration],
        frequentPushesEnabled: Bool
    ) async throws {
        let identity = try requireIdentity()
        try await requestWithoutResponse(
            .activitySync(identity.deviceID),
            body: ActivitySyncBody(
                activities: activities,
                frequentPushesEnabled: frequentPushesEnabled
            )
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
        let (data, response) = try await performRequest(
            endpoint,
            body: body,
            authenticated: authenticated
        )
        guard 200..<300 ~= response.statusCode else {
            throw APIError.httpStatus(response.statusCode)
        }
        return data
    }

    private func historyPage<Element: Decodable & Sendable>(
        _ endpoint: DeviceAPIEndpoint,
        cursor: String?,
        limit: Int,
        machineID: String?
    ) async throws -> HistoryPage<Element> {
        var queryItems = [URLQueryItem(name: "limit", value: String(limit))]
        if let cursor {
            queryItems.append(URLQueryItem(name: "cursor", value: cursor))
        }
        if let machineID {
            queryItems.append(URLQueryItem(name: "machine_id", value: machineID))
        }
        let (data, response) = try await performRequest(
            endpoint,
            body: Optional<EmptyBody>.none,
            authenticated: true,
            queryItems: queryItems
        )
        guard 200..<300 ~= response.statusCode else {
            throw APIError.httpStatus(response.statusCode)
        }
        return try JSONDecoder.runBuoy.decode(HistoryPage<Element>.self, from: data)
    }

    private func performRequest<Body: Encodable>(
        _ endpoint: DeviceAPIEndpoint,
        body: Body?,
        authenticated: Bool,
        queryItems: [URLQueryItem] = [],
        headers: [String: String] = [:]
    ) async throws -> (Data, HTTPURLResponse) {
        let baseURL = baseURLProvider()
        guard let endpointURL = URL(string: endpoint.path, relativeTo: baseURL)?.absoluteURL,
              var components = URLComponents(url: endpointURL, resolvingAgainstBaseURL: false)
        else {
            throw APIError.invalidURL
        }
        if !queryItems.isEmpty {
            components.queryItems = queryItems
        }
        guard let url = components.url else { throw APIError.invalidURL }
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
        for (field, value) in headers {
            request.setValue(value, forHTTPHeaderField: field)
        }

        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse else {
            throw APIError.invalidResponse
        }
        return (data, response)
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
        let generation: Int?

        init(token: String, generation: Int? = nil) {
            self.token = token
            self.generation = generation
        }
    }

    private struct ClaimBody: Encodable {
        let challenge: String
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
        let frequentPushesEnabled: Bool

        private enum CodingKeys: String, CodingKey {
            case activities
            case frequentPushesEnabled = "frequent_pushes_enabled"
        }
    }

    private struct EmptyBody: Encodable {}
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

    var isSyncUnsupported: Bool {
        guard case .httpStatus(let status) = self else { return false }
        return status == 404 || status == 405 || status == 501
    }
}
