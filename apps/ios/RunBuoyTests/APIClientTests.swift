import Foundation
import XCTest
@testable import RunBuoyApp

final class APIClientTests: XCTestCase {
    override func tearDown() {
        URLProtocolStub.handler = nil
        super.tearDown()
    }

    func testReadCollectionsAndDetailUseCanonicalShapes() async throws {
        let api = makeAPI { request in
            switch request.url?.path {
            case "/v1/runs":
                return (200, try FixtureLoader.data("runs"))
            case "/v1/runs/018f0d8a-8c0a-7000-8000-000000000001":
                return (200, try FixtureLoader.data("run-detail"))
            case "/v1/machines":
                return (200, try FixtureLoader.data("machines"))
            case "/v1/notifications":
                return (200, try FixtureLoader.data("messages"))
            default:
                return (404, Data())
            }
        }

        let id = UUID(uuidString: "018f0d8a-8c0a-7000-8000-000000000001")!
        async let runs = api.listRuns()
        async let machines = api.listMachines()
        async let messages = api.listMessages()
        async let detail = api.runDetail(id: id)

        let result = try await (runs, machines, messages, detail)
        XCTAssertEqual(result.0.count, 1)
        XCTAssertEqual(result.1.count, 2)
        XCTAssertEqual(result.2.count, 1)
        XCTAssertEqual(result.3.feed.map(\.sequence), [1, 42])
    }

    func testRevisionedSyncSendsCursorAndETagAndDecodesSnapshot() async throws {
        var captured: URLRequest?
        let api = makeAPI { request in
            captured = request
            return (
                200,
                Data(
                    #"{"schema_version":1,"next_cursor":42,"server_time":"2026-08-07T10:00:00Z","runs":[],"machines":[],"notifications":[],"history_runs_next_cursor":"runs-next","history_runs_has_more":true,"history_notifications_next_cursor":null,"history_notifications_has_more":false}"#.utf8
                )
            )
        }

        let result = try await api.sync(cursor: 41)

        guard case .snapshot(let snapshot) = result else {
            return XCTFail("Expected a sync snapshot")
        }
        XCTAssertEqual(snapshot.nextCursor, 42)
        XCTAssertEqual(snapshot.historyRunsNextCursor, "runs-next")
        XCTAssertTrue(snapshot.historyRunsHasMore)
        XCTAssertEqual(captured?.url?.path, "/v1/sync")
        XCTAssertEqual(captured?.url?.query, "cursor=41")
        XCTAssertEqual(
            captured?.value(forHTTPHeaderField: "If-None-Match"),
            "\"sync-workspace_1-41\""
        )
    }

    func testRevisionedSyncAcceptsNotModified() async throws {
        let api = makeAPI { _ in (304, Data()) }

        let result = try await api.sync(cursor: 9)

        XCTAssertEqual(result, .notModified)
    }

    func testHistoryPageCarriesStableCursorAndMachineFilter() async throws {
        var captured: URLRequest?
        let api = makeAPI { request in
            captured = request
            return (200, Data(#"{"items":[],"next_cursor":"next","has_more":true}"#.utf8))
        }

        let page = try await api.historyRuns(
            cursor: "opaque cursor",
            limit: 50,
            machineID: "machine/one"
        )

        XCTAssertEqual(page.nextCursor, "next")
        XCTAssertTrue(page.hasMore)
        XCTAssertEqual(captured?.url?.path, "/v1/history/runs")
        let components = try XCTUnwrap(
            captured?.url.flatMap { URLComponents(url: $0, resolvingAgainstBaseURL: false) }
        )
        XCTAssertEqual(
            Dictionary(uniqueKeysWithValues: (components.queryItems ?? []).map { ($0.name, $0.value) })[
                "cursor"
            ],
            "opaque cursor"
        )
        XCTAssertEqual(
            Dictionary(uniqueKeysWithValues: (components.queryItems ?? []).map { ($0.name, $0.value) })[
                "machine_id"
            ],
            "machine/one"
        )
    }

    func testActivityTokenRegistrationCarriesOwnershipAndGeneration() async throws {
        var captured: URLRequest?
        let api = makeAPI { request in
            captured = request
            return (204, Data())
        }

        try await api.registerActivityToken(
            "feedface",
            activityID: "activity_1",
            runID: "018f0d8a-8c0a-7000-8000-000000000001",
            generation: 3
        )

        XCTAssertEqual(captured?.httpMethod, "PUT")
        XCTAssertEqual(captured?.url?.path, "/v1/live-activities/activity_1/update-token")
        let object = try XCTUnwrap(captured?.httpBody)
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: object) as? [String: Any])
        XCTAssertEqual(body["token"] as? String, "feedface")
        XCTAssertEqual(body["device_id"] as? String, "device_1")
        XCTAssertEqual(body["run_id"] as? String, "018f0d8a-8c0a-7000-8000-000000000001")
        XCTAssertEqual(body["generation"] as? Int, 3)
    }

    func testActivityReconciliationCarriesLifecycleStateAndSequence() async throws {
        var captured: URLRequest?
        let api = makeAPI { request in
            captured = request
            return (204, Data())
        }

        try await api.syncActivities(
            [
                ActivityRegistration(
                    activityID: "activity_1",
                    runID: "018f0d8a-8c0a-7000-8000-000000000001",
                    updateToken: "feedface",
                    tokenGeneration: 3,
                    state: "stale",
                    lastSequence: 42
                )
            ],
            frequentPushesEnabled: false
        )

        XCTAssertEqual(captured?.httpMethod, "POST")
        XCTAssertEqual(captured?.url?.path, "/v1/devices/device_1/activity-sync")
        let data = try XCTUnwrap(captured?.httpBody)
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        let activities = try XCTUnwrap(body["activities"] as? [[String: Any]])
        XCTAssertEqual(activities[0]["update_token"] as? String, "feedface")
        XCTAssertEqual(activities[0]["token_generation"] as? Int, 3)
        XCTAssertEqual(activities[0]["state"] as? String, "stale")
        XCTAssertEqual(activities[0]["last_sequence"] as? Int, 42)
        XCTAssertEqual(body["frequent_pushes_enabled"] as? Bool, false)
    }

    func testPushToStartRegistrationCarriesGeneration() async throws {
        var captured: URLRequest?
        let api = makeAPI { request in
            captured = request
            return (204, Data())
        }

        try await api.registerPushToStartToken("feedface", generation: 4)

        let data = try XCTUnwrap(captured?.httpBody)
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(body["token"] as? String, "feedface")
        XCTAssertEqual(body["generation"] as? Int, 4)
    }

    func testIdentityLifecycleUsesOwnedEndpointsAndDeletionChallengeBody() async throws {
        var captured: [URLRequest] = []
        let api = makeAPI { request in
            captured.append(request)
            if request.url?.path == "/v1/workspaces/workspace_1/deletion-challenge" {
                return (
                    200,
                    Data(
                        #"{"challenge":"single-use","expires_at":"2026-08-07T12:00:00Z"}"#.utf8
                    )
                )
            }
            return (204, Data())
        }

        try await api.resetDevice()
        try await api.revokeMachine("machine_one")
        let challenge = try await api.requestWorkspaceDeletionChallenge()
        try await api.deleteWorkspace(challenge: challenge.challenge)

        XCTAssertEqual(challenge.challenge, "single-use")
        XCTAssertEqual(
            captured.map(\.httpMethod),
            ["DELETE", "POST", "POST", "DELETE"]
        )
        XCTAssertEqual(
            captured.compactMap { $0.url?.path },
            [
                "/v1/devices/device_1",
                "/v1/machines/machine_one/revoke",
                "/v1/workspaces/workspace_1/deletion-challenge",
                "/v1/workspaces/workspace_1"
            ]
        )
        let challengeBody = try XCTUnwrap(captured[2].httpBody)
        let challengeJSON = try XCTUnwrap(
            JSONSerialization.jsonObject(with: challengeBody) as? [String: String]
        )
        XCTAssertEqual(challengeJSON, ["confirmation": "DELETE"])
        let deleteBody = try XCTUnwrap(captured[3].httpBody)
        let deleteJSON = try XCTUnwrap(
            JSONSerialization.jsonObject(with: deleteBody) as? [String: String]
        )
        XCTAssertEqual(deleteJSON, ["challenge": "single-use"])
    }

    func testDeviceSurfaceContainsOnlyReadAndReceivingPlaneOperations() {
        let endpoints: [DeviceAPIEndpoint] = [
            .bootstrap,
            .runs,
            .run(UUID()),
            .machines,
            .messages,
            .sync,
            .historyRuns,
            .historyMessages,
            .claimPairing("pair"),
            .notificationToken("device"),
            .pushToStartToken("device"),
            .activityToken("activity"),
            .activitySync("device"),
            .preferences,
            .subscription("subscription"),
            .resetDevice("device"),
            .revokeMachine("machine"),
            .workspaceDeletionChallenge("workspace"),
            .deleteWorkspace("workspace")
        ]

        XCTAssertEqual(endpoints.count, 19)
        XCTAssertEqual(endpoints.filter { $0.method == "GET" }.count, 7)
        XCTAssertTrue(endpoints.allSatisfy { $0.path.hasPrefix("/v1/") })
    }

    func testServerAddressUsesBundledServerWhenSettingIsEmpty() {
        let bundledURL = URL(string: "https://api.runbuoy.cloud")!

        let resolved = AppConfiguration.resolvedAPIBaseURL(
            serverAddress: "  ",
            defaultBaseURL: bundledURL
        )

        XCTAssertEqual(resolved, bundledURL)
        XCTAssertEqual(AppConfiguration.displayAddress(for: bundledURL), "api.runbuoy.cloud")
    }

    func testServerIPAddressPreservesSSLIPDeploymentConvention() {
        let resolved = AppConfiguration.resolvedAPIBaseURL(
            serverAddress: "203.0.113.42",
            defaultBaseURL: URL(string: "https://198-51-100-7.sslip.io")!
        )

        XCTAssertEqual(resolved?.absoluteString, "https://203-0-113-42.sslip.io")
        XCTAssertEqual(resolved.map(AppConfiguration.displayAddress(for:)), "203.0.113.42")
    }

    func testServerAddressAcceptsExplicitHTTPURLAndRejectsInvalidValue() {
        let bundledURL = URL(string: "https://api.runbuoy.cloud")!

        let explicitURL = AppConfiguration.resolvedAPIBaseURL(
            serverAddress: "http://192.168.1.8:8080",
            defaultBaseURL: bundledURL
        )
        let invalidURL = AppConfiguration.resolvedAPIBaseURL(
            serverAddress: "not a server/path",
            defaultBaseURL: bundledURL
        )

        XCTAssertEqual(explicitURL?.absoluteString, "http://192.168.1.8:8080")
        XCTAssertNil(invalidURL)
    }

    private func makeAPI(
        handler: @escaping (URLRequest) throws -> (Int, Data)
    ) -> URLSessionRunBuoyAPI {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [URLProtocolStub.self]
        URLProtocolStub.handler = handler
        return URLSessionRunBuoyAPI(
            baseURL: URL(string: "https://api.test.runbuoy.dev")!,
            session: URLSession(configuration: configuration),
            identityStore: TestIdentityStore()
        )
    }
}

private struct TestIdentityStore: DeviceIdentityStoring {
    func load() throws -> DeviceIdentity? {
        DeviceIdentity(deviceID: "device_1", workspaceID: "workspace_1", credential: "device-credential")
    }
    func save(_ identity: DeviceIdentity) throws {}
    func remove() throws {}
}

private final class URLProtocolStub: URLProtocol {
    static var handler: ((URLRequest) throws -> (Int, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        do {
            var capturedRequest = request
            if capturedRequest.httpBody == nil, let stream = capturedRequest.httpBodyStream {
                capturedRequest.httpBody = try Self.readBody(from: stream)
            }
            let result = try Self.handler?(capturedRequest) ?? (500, Data())
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: result.0,
                httpVersion: "HTTP/1.1",
                headerFields: ["Content-Type": "application/json"]
            )!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: result.1)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}

    private static func readBody(from stream: InputStream) throws -> Data {
        stream.open()
        defer { stream.close() }

        var body = Data()
        var buffer = [UInt8](repeating: 0, count: 4_096)
        while true {
            let count = stream.read(&buffer, maxLength: buffer.count)
            if count < 0 {
                throw stream.streamError ?? URLError(.cannotDecodeContentData)
            }
            if count == 0 {
                break
            }
            body.append(contentsOf: buffer.prefix(count))
        }
        return body
    }
}
