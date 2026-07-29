import XCTest
@testable import RunBuoyApp

@MainActor
final class UITestScenarioTests: XCTestCase {
    func testPreviewScenariosSeedDeterministicStates() {
        let loaded = PreviewFixtures.store(scenario: .loaded)
        XCTAssertEqual(loaded.state, .loaded)
        XCTAssertEqual(loaded.runs.map(\.id), [
            PreviewFixtures.activeRun.id,
            PreviewFixtures.failedRun.id
        ])

        let empty = PreviewFixtures.store(scenario: .empty)
        XCTAssertEqual(empty.state, .loaded)
        XCTAssertTrue(empty.runs.isEmpty)
        XCTAssertTrue(empty.machines.isEmpty)
        XCTAssertTrue(empty.messages.isEmpty)

        let offline = PreviewFixtures.store(scenario: .offline)
        XCTAssertEqual(offline.state, .offline("UI test offline fixture"))
        XCTAssertFalse(offline.runs.isEmpty)

        let failed = PreviewFixtures.store(scenario: .failed)
        XCTAssertEqual(failed.state, .failed("UI test failure fixture"))
        XCTAssertTrue(failed.runs.isEmpty)
    }
}
