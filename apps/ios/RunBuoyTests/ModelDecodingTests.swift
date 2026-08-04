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
        XCTAssertLessThan(detail.run.createdAt, detail.run.startedAt)
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
        XCTAssertEqual(state.machineName, "Mac Studio")
        XCTAssertNotNil(state.createdAt)
        XCTAssertNotNil(state.estimatedEndAt)
    }

    func testRunSnapshotProjectsToMatchingLiveActivityContent() throws {
        let detail = try JSONDecoder.runBuoy.decode(
            RunDetail.self,
            from: FixtureLoader.data("run-detail")
        )

        let state = RunLiveActivityProjection.contentState(for: detail.run)

        XCTAssertEqual(state.sequence, detail.run.sequence)
        XCTAssertEqual(state.executionStatus, detail.run.executionStatus.rawValue)
        XCTAssertEqual(state.progress, detail.run.progress?.fraction)
        XCTAssertEqual(state.updatedAt, detail.run.updatedAt)
        XCTAssertEqual(state.machineName, detail.run.machineName)
    }

    func testConfirmedDurationUsesCreationAndLastMachineUpdate() {
        let created = Date(timeIntervalSince1970: 1_000)
        let started = created.addingTimeInterval(2)
        let confirmed = created.addingTimeInterval(75)

        XCTAssertEqual(
            RunActivityDurationText.string(
                createdAt: created,
                startedAt: started,
                updatedAt: confirmed
            ),
            "1:15"
        )
        XCTAssertEqual(
            RunActivityDurationText.string(
                createdAt: created,
                startedAt: started,
                updatedAt: created.addingTimeInterval(3_661)
            ),
            "1:01:01"
        )
    }

    func testRunDurationUsesStartAndLatestMachineConfirmation() {
        let started = Date(timeIntervalSince1970: 1_000)

        XCTAssertEqual(
            RunDurationText.string(
                from: started,
                to: started.addingTimeInterval(75)
            ),
            "1:15"
        )
        XCTAssertEqual(
            RunDurationText.string(
                from: started,
                to: started.addingTimeInterval(3_661)
            ),
            "1:01:01"
        )
    }

    func testLiveActivityContentStateKeepsOldPayloadCompatibility() throws {
        let data = Data(
            """
            {
              "sequence": 1,
              "executionStatus": "RUNNING",
              "healthStatus": "HEALTHY",
              "attentionStatus": "NONE",
              "progressKind": "indeterminate",
              "startedAt": "2026-07-29T08:00:00Z",
              "updatedAt": "2026-07-29T08:00:15Z"
            }
            """.utf8
        )

        let state = try JSONDecoder().decode(
            RunActivityAttributes.ContentState.self,
            from: data
        )

        XCTAssertNil(state.createdAt)
        XCTAssertNil(state.machineName)
        XCTAssertEqual(
            RunActivityDurationText.string(
                createdAt: state.createdAt,
                startedAt: state.startedAt,
                updatedAt: state.updatedAt
            ),
            "0:15"
        )
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
