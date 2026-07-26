import ActivityKit
import XCTest
@testable import RunBuoyApp

final class ModelDecodingTests: XCTestCase {
    func testRunDetailDecodesProtocolFixtureAndLastSequence() throws {
        let detail = try JSONDecoder.runBuoy.decode(
            RunDetail.self,
            from: FixtureLoader.data("run-detail")
        )

        XCTAssertEqual(detail.run.sequence, 42)
        XCTAssertEqual(detail.run.progress?.boundedFraction, 0.37)
        XCTAssertNotNil(detail.run.estimatedEndAt)
        XCTAssertEqual(detail.run.healthStatus, .healthy)
        XCTAssertEqual(detail.feed.map(\.sequence), [42, 1])
    }

    func testUnknownExecutionStateIsForwardCompatible() throws {
        let runs = try JSONDecoder.runBuoy.decode(
            [RunSnapshot].self,
            from: FixtureLoader.data("runs")
        )

        XCTAssertEqual(runs.first?.executionStatus, .unknown)
        XCTAssertEqual(runs.first?.healthStatus, .stale)
        XCTAssertEqual(runs.first?.sequence, 9)
    }

    func testMachineProjectionToleratesAbsentSubscriptionFields() throws {
        let machines = try JSONDecoder.runBuoy.decode(
            [MachineSnapshot].self,
            from: FixtureLoader.data("machines")
        )

        XCTAssertEqual(machines.count, 2)
        XCTAssertFalse(machines[0].isSubscribed)
        XCTAssertNil(machines[0].subscriptionID)
        XCTAssertTrue(machines[1].isSubscribed)
    }

    func testRichFieldsAcceptServerLabelKeyAndRemainPlainText() throws {
        let messages = try JSONDecoder.runBuoy.decode(
            [RichMessage].self,
            from: FixtureLoader.data("messages")
        )

        XCTAssertEqual(messages[0].fields[0].name, "Artifacts")
        XCTAssertEqual(messages[0].body, "<script>plain text only</script>")
    }

    func testLiveActivityContentStateDecodesISO8601Dates() throws {
        let state = try JSONDecoder().decode(
            RunActivityAttributes.ContentState.self,
            from: FixtureLoader.data("live-content-state")
        )

        XCTAssertEqual(state.sequence, 42)
        XCTAssertEqual(state.current, 37)
        XCTAssertEqual(state.healthStatus, "STALE")
        XCTAssertNotNil(state.estimatedEndAt)
    }

    func testProgressFractionIsBoundedForRendering() {
        let progress = RunProgress(
            kind: .determinate,
            current: 125,
            total: 100,
            fraction: 1.25,
            unit: "items",
            source: "explicit"
        )

        XCTAssertEqual(progress.boundedFraction, 1)
    }

    func testLongEnglishAndChineseFixturesPreserveContent() {
        XCTAssertGreaterThan(PreviewFixtures.longEnglishDetail.run.title.count, 70)
        XCTAssertGreaterThan(PreviewFixtures.longChineseDetail.run.safeMessage?.count ?? 0, 30)
    }
}
