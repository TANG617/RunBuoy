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

    func testDeviceSurfaceContainsOnlyReadAndReceivingPlaneOperations() {
        let endpoints: [DeviceAPIEndpoint] = [
            .bootstrap,
            .runs,
            .run(UUID()),
            .machines,
            .messages,
            .claimPairing("pair"),
            .notificationToken("device"),
            .pushToStartToken("device"),
            .activityToken("activity"),
            .activitySync("device"),
            .preferences,
            .subscription("subscription")
        ]

        XCTAssertEqual(endpoints.count, 12)
        XCTAssertEqual(endpoints.filter { $0.method == "GET" }.count, 4)
        XCTAssertTrue(endpoints.allSatisfy { $0.path.hasPrefix("/v1/") })
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
            let result = try Self.handler?(request) ?? (500, Data())
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
}
