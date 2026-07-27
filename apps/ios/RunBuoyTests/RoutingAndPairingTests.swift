import XCTest
@testable import RunBuoyApp

@MainActor
final class RoutingAndPairingTests: XCTestCase {
    func testRunDeepLinkSelectsRunsAndRoutesToDetail() throws {
        let id = UUID(uuidString: "018f0d8a-8c0a-7000-8000-000000000001")!
        let router = AppRouter()
        router.selectedTab = .settings

        XCTAssertTrue(router.handle(URL(string: "runbuoy://runs/\(id.uuidString)")!))
        XCTAssertEqual(router.selectedTab, .activeRuns)
        XCTAssertEqual(router.activeRunsPath, [.runDetail(id)])
    }

    func testUnrelatedURLIsNotConsumed() {
        let router = AppRouter()
        XCTAssertFalse(router.handle(URL(string: "https://example.com/runs/1")!))
        XCTAssertTrue(router.activeRunsPath.isEmpty)
    }

    func testPairDeepLinkOpensConfirmationWithoutClaiming() throws {
        let router = AppRouter()
        let url = URL(
            string: "runbuoy://pair/session_123?challenge=once-only&machine=Mac%20Studio&platform=macOS"
        )!

        XCTAssertTrue(router.handle(url))
        XCTAssertEqual(router.selectedTab, .settings)
        XCTAssertEqual(router.settingsPath, [.pairMachine])
        XCTAssertEqual(router.pendingPairingCode?.sessionID, "session_123")
        XCTAssertEqual(router.pendingPairingCode?.challenge, "once-only")
    }

    func testCanonicalPairingURL() throws {
        let code = try PairingCode.decode(
            "runbuoy://pair/session_123?challenge=once-only&machine=Mac%20Studio&platform=macOS"
        )

        XCTAssertEqual(code.sessionID, "session_123")
        XCTAssertEqual(code.challenge, "once-only")
        XCTAssertEqual(code.machineDisplayName, "Mac Studio")
        XCTAssertEqual(code.platform, "macOS")
    }

    func testQuerySessionPairingURLCompatibility() throws {
        let code = try PairingCode.decode(
            "runbuoy://pair?session=session_456&challenge=c&machine=Builder"
        )
        XCTAssertEqual(code.sessionID, "session_456")
    }

    func testJSONPairingPayloadCompatibility() throws {
        let code = try PairingCode.decode(
            #"{"pairing_session_id":"session_789","challenge":"c","machine_display_name":"Linux Builder","platform":"linux"}"#
        )
        XCTAssertEqual(code.machineDisplayName, "Linux Builder")
    }
}
