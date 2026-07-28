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

    func testHomeTabsDoNotIncludeMachines() {
        XCTAssertEqual(AppTab.allCases, [.activeRuns, .history, .settings])
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

    func testMachineIconsExposeOnlySupportedSymbols() {
        XCTAssertEqual(
            MachineIcon.allCases.map(\.rawValue),
            [
                "desktopcomputer",
                "macpro.gen3.server",
                "macbook",
                "macmini",
                "macstudio",
                "macpro.gen2"
            ]
        )
    }

    func testMachineIconSelectionIsStoredPerMachine() throws {
        let suiteName = "MachineIconTests.\(UUID().uuidString)"
        let userDefaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { userDefaults.removePersistentDomain(forName: suiteName) }

        XCTAssertEqual(
            MachineIcon.selected(for: "machine_a", userDefaults: userDefaults),
            .desktopcomputer
        )

        userDefaults.set(
            MachineIcon.macStudio.rawValue,
            forKey: MachineIcon.key(for: "machine_a")
        )

        XCTAssertEqual(
            MachineIcon.selected(for: "machine_a", userDefaults: userDefaults),
            .macStudio
        )
        XCTAssertEqual(
            MachineIcon.selected(for: "machine_b", userDefaults: userDefaults),
            .desktopcomputer
        )
    }
}

@MainActor
final class HistoryFilteringTests: XCTestCase {
    func testMachineOptionsMergeSourcesAndPreferLocalLabels() throws {
        let suiteName = "HistoryFilteringTests.\(UUID().uuidString)"
        let userDefaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { userDefaults.removePersistentDomain(forName: suiteName) }
        userDefaults.set(
            "A Local Mac",
            forKey: MachineLocalLabel.key(for: PreviewFixtures.machine.id)
        )
        let messageOnly = RichMessage(
            id: "notification_message_only",
            machineID: "machine_message_only",
            title: "Message",
            subtitle: nil,
            body: "Body",
            level: "info",
            fields: [],
            createdAt: PreviewFixtures.baseDate,
            expiresAt: nil
        )

        let options = HistoryMachineOption.makeOptions(
            machines: [PreviewFixtures.machine],
            runs: [PreviewFixtures.activeRun, PreviewFixtures.failedRun],
            messages: [PreviewFixtures.message, messageOnly],
            userDefaults: userDefaults
        )

        XCTAssertEqual(
            options,
            [
                HistoryMachineOption(id: PreviewFixtures.machine.id, name: "A Local Mac"),
                HistoryMachineOption(id: PreviewFixtures.failedRun.machineID, name: "CI Builder"),
                HistoryMachineOption(id: "machine_message_only", name: "machine_message_only")
            ]
        )
    }

    func testSelectedMachineFiltersRunsAndMessagesIncludingUnscopedMessages() {
        let unscopedMessage = RichMessage(
            id: "notification_unscoped",
            machineID: nil,
            title: "Workspace message",
            subtitle: nil,
            body: "Body",
            level: "info",
            fields: [],
            createdAt: PreviewFixtures.baseDate,
            expiresAt: nil
        )
        let runs = [PreviewFixtures.activeRun, PreviewFixtures.failedRun]
        let messages = [PreviewFixtures.message, PreviewFixtures.ciMessage, unscopedMessage]

        let all = HistoryContentFilter(machineID: nil)
        XCTAssertEqual(runs.filter { all.includes(machineID: $0.machineID) }, runs)
        XCTAssertEqual(messages.filter { all.includes(machineID: $0.machineID) }, messages)

        let selected = HistoryContentFilter(machineID: PreviewFixtures.ciMachine.id)
        XCTAssertEqual(
            runs.filter { selected.includes(machineID: $0.machineID) },
            [PreviewFixtures.failedRun]
        )
        XCTAssertEqual(
            messages.filter { selected.includes(machineID: $0.machineID) },
            [PreviewFixtures.ciMessage]
        )
    }
}
