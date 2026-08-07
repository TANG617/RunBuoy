import XCTest

final class RunBuoyUITests: XCTestCase {
    private var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
    }

    override func tearDownWithError() throws {
        if app.state != .notRunning {
            let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
            attachment.name = "\(name)-final-screen"
            attachment.lifetime = .deleteOnSuccess
            add(attachment)
            app.terminate()
        }
        app = nil
    }

    func testOnboardingCompletesWithSeededPairingCode() {
        launch(
            onboarding: true,
            initialURL: Self.pairingURL
        )

        XCTAssertTrue(element("onboarding.page.product").waitForExistence(timeout: 5))
        element("onboarding.primary-action").tap()
        XCTAssertTrue(element("onboarding.page.region").waitForExistence(timeout: 2))
        app.segmentedControls.buttons["Global"].tap()

        element("onboarding.primary-action").tap()
        XCTAssertTrue(element("onboarding.page.permissions").waitForExistence(timeout: 2))

        element("onboarding.primary-action").tap()
        XCTAssertTrue(element("onboarding.page.pairing").waitForExistence(timeout: 2))
        XCTAssertTrue(element("onboarding.pairing-identity").exists)

        element("onboarding.primary-action").tap()
        XCTAssertTrue(element("onboarding.pairing-success").waitForExistence(timeout: 2))

        element("onboarding.primary-action").tap()
        XCTAssertTrue(element("screen.activeRuns").waitForExistence(timeout: 3))
    }

    func testActiveRunOpensDetailAndNavigatesBack() {
        launch()

        let activeRow = element("run.row.\(Self.activeRunID)")
        XCTAssertTrue(activeRow.waitForExistence(timeout: 5))
        XCTAssertTrue(activeRow.label.contains("Run time"))
        XCTAssertTrue(activeRow.label.contains("Heartbeat"))
        activeRow.tap()

        XCTAssertTrue(element("screen.runDetail").waitForExistence(timeout: 3))
        element("screen.runDetail").swipeDown()
        XCTAssertTrue(element("screen.runDetail").exists)
        app.navigationBars.buttons.element(boundBy: 0).tap()
        XCTAssertTrue(element("screen.activeRuns").waitForExistence(timeout: 3))
    }

    func testColdLaunchURLRoutesToRunDetail() {
        launch(initialURL: "runbuoy://runs/\(Self.activeRunID)")

        XCTAssertTrue(element("screen.runDetail").waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Gurobi experiment"].exists)
    }

    func testHistoryFiltersRunsAndMessagesByMachine() {
        launch()
        tapTab("tab.history", label: "History")

        XCTAssertTrue(element("screen.history").waitForExistence(timeout: 3))
        let macMessage = element("history.message.notification_1")
        let ciMessage = element("history.message.notification_2")
        XCTAssertTrue(macMessage.exists)
        XCTAssertTrue(ciMessage.exists)

        element("history.filter.machine_ci").tap()

        XCTAssertTrue(ciMessage.waitForExistence(timeout: 2))
        XCTAssertTrue(macMessage.waitForNonExistence(timeout: 2))
        XCTAssertTrue(element("run.row.\(Self.failedRunID)").exists)
    }

    func testHistoryLoadsMachineFiltersWhenInitialSnapshotIsEmpty() {
        launch(scenario: "empty")
        tapTab("tab.history", label: "History")

        XCTAssertTrue(
            element("history.filter.machine_ci").waitForExistence(timeout: 3)
        )
    }

    func testNotificationPreferencePersistsAcrossRelaunch() {
        launch()
        tapTab("tab.settings", label: "Settings")

        let toggle = element("settings.notifications")
        XCTAssertTrue(toggle.waitForExistence(timeout: 3))
        XCTAssertEqual(toggle.value as? String, "1")
        toggle.coordinate(
            withNormalizedOffset: CGVector(dx: 0.9, dy: 0.5)
        ).tap()
        waitForValue("0", of: toggle)

        app.terminate()
        launch(resetState: false)
        tapTab("tab.settings", label: "Settings")

        let relaunchedToggle = element("settings.notifications")
        XCTAssertTrue(relaunchedToggle.waitForExistence(timeout: 3))
        XCTAssertEqual(relaunchedToggle.value as? String, "0")
    }

    func testMachineNameIsReadOnlyAndMatchesServer() {
        launch()
        openMachines()

        element("machine.row.machine_mac_studio").tap()
        XCTAssertTrue(element("screen.machineDetail").waitForExistence(timeout: 3))

        XCTAssertTrue(app.navigationBars["Mac Studio"].waitForExistence(timeout: 3))
        XCTAssertFalse(element("machine.localLabel").exists)
    }

    func testMachineStopReceivingAndRevokeHaveDistinctDestructiveConfirmations() {
        launch()
        openMachines()

        element("machine.row.machine_mac_studio").tap()
        XCTAssertTrue(element("screen.machineDetail").waitForExistence(timeout: 3))

        let stopReceiving = element("machine.stopReceiving")
        if !stopReceiving.isHittable {
            element("screen.machineDetail").swipeUp()
        }
        XCTAssertTrue(stopReceiving.waitForExistence(timeout: 3))
        stopReceiving.tap()
        XCTAssertTrue(
            app.staticTexts[
                "Only this iPhone’s subscription is removed. The computer stays paired and other devices are unaffected."
            ].waitForExistence(timeout: 2)
        )

        // Relaunch instead of relying on the system action sheet's cancel
        // accessibility node, which differs across iOS 18 and the latest SDK.
        app.terminate()
        launch()
        openMachines()
        element("machine.row.machine_mac_studio").tap()
        XCTAssertTrue(element("screen.machineDetail").waitForExistence(timeout: 3))

        let revoke = element("machine.revoke")
        if !revoke.isHittable {
            element("screen.machineDetail").swipeUp()
        }
        waitForHittable(revoke)
        revoke.tap()
        XCTAssertTrue(
            app.staticTexts
                .matching(
                    NSPredicate(
                        format: "label CONTAINS %@",
                        "immediately invalidates the computer and webhook credentials"
                    )
                )
                .firstMatch
                .waitForExistence(timeout: 2)
        )
    }

    func testManualPairingCodeCanBeConfirmed() {
        launch()
        openMachines()

        element("machines.enterPairingCode").tap()
        let codeField = element("pairing.code")
        XCTAssertTrue(codeField.waitForExistence(timeout: 3))
        codeField.typeText(Self.pairingURL)
        element("pairing.continue").tap()

        let claimButton = element("pairing.claim")
        XCTAssertTrue(claimButton.waitForExistence(timeout: 3))
        XCTAssertTrue(element("pairing.machineName").exists)
        claimButton.tap()

        XCTAssertTrue(element("screen.machines").waitForExistence(timeout: 3))
        XCTAssertTrue(element("screen.pairMachine").waitForNonExistence(timeout: 3))
    }

    func testClearCacheShowsCompletionFeedback() {
        launch()
        tapTab("tab.settings", label: "Settings")

        let clearButton = element("settings.clearCache")
        XCTAssertTrue(clearButton.waitForExistence(timeout: 3))
        clearButton.tap()

        XCTAssertTrue(element("settings.cacheCleared").waitForExistence(timeout: 3))
    }

    func testCapabilityDemoOpensFromSettings() {
        launch()
        tapTab("tab.settings", label: "Settings")

        let featureTour = element("settings.capabilityDemo")
        XCTAssertTrue(featureTour.waitForExistence(timeout: 3))
        featureTour.tap()

        XCTAssertTrue(element("screen.capabilityDemo").waitForExistence(timeout: 3))
        XCTAssertTrue(element("demo.startLiveActivity").exists)
    }

    func testAccessibilityAuditForCoreScreensAndScenarios() throws {
        launch()
        XCTAssertTrue(element("screen.activeRuns").waitForExistence(timeout: 5))
        try auditCurrentScreen()

        element("run.row.\(Self.activeRunID)").tap()
        XCTAssertTrue(element("screen.runDetail").waitForExistence(timeout: 3))
        try auditCurrentScreen()

        app.navigationBars.buttons.element(boundBy: 0).tap()
        tapTab("tab.history", label: "History")
        XCTAssertTrue(element("screen.history").waitForExistence(timeout: 3))
        try auditCurrentScreen()

        tapTab("tab.settings", label: "Settings")
        XCTAssertTrue(element("screen.settings").waitForExistence(timeout: 3))
        try auditCurrentScreen()

        element("settings.capabilityDemo").tap()
        XCTAssertTrue(element("screen.capabilityDemo").waitForExistence(timeout: 3))
        try auditCurrentScreen()
        app.navigationBars.buttons.element(boundBy: 0).tap()
        XCTAssertTrue(element("screen.settings").waitForExistence(timeout: 3))

        app.swipeUp()
        waitForHittable(element("settings.clearCache"))
        try auditCurrentScreen()

        app.swipeUp()
        try auditCurrentScreen()

        app.swipeDown()
        app.swipeDown()
        waitForHittable(element("settings.machines"))
        openMachines(fromSettings: true)
        try auditCurrentScreen()

        launch(scenario: "empty")
        XCTAssertTrue(element("activeRuns.state.empty").waitForExistence(timeout: 3))
        try auditCurrentScreen()

        launch(scenario: "offline")
        XCTAssertTrue(element("runs.offlineBanner").waitForExistence(timeout: 3))
        try auditCurrentScreen()

        launch(scenario: "failed")
        XCTAssertTrue(element("activeRuns.state.failed").waitForExistence(timeout: 3))
        try auditCurrentScreen()
    }

    private func launch(
        scenario: String = "loaded",
        resetState: Bool = true,
        onboarding: Bool = false,
        initialURL: String? = nil
    ) {
        if app.state != .notRunning {
            app.terminate()
        }
        app = XCUIApplication()
        app.launchArguments = [
            "-runbuoy-ui-testing",
            "-runbuoy-ui-scenario", scenario,
            "-AppleLanguages", "(en)",
            "-AppleLocale", "en_US"
        ]
        if resetState {
            app.launchArguments.append("-runbuoy-ui-reset-state")
        }
        if onboarding {
            app.launchArguments.append("-runbuoy-ui-onboarding")
        }
        if let initialURL {
            app.launchArguments += ["-runbuoy-ui-url", initialURL]
        }
        app.launch()
        XCTAssertEqual(app.state, .runningForeground)
    }

    private func openMachines(fromSettings: Bool = false) {
        if !fromSettings {
            tapTab("tab.settings", label: "Settings")
            XCTAssertTrue(element("screen.settings").waitForExistence(timeout: 3))
        }
        element("settings.machines").tap()
        XCTAssertTrue(element("screen.machines").waitForExistence(timeout: 3))
    }

    private func element(_ identifier: String) -> XCUIElement {
        app.descendants(matching: .any)
            .matching(identifier: identifier)
            .firstMatch
    }

    private func tapTab(
        _ identifier: String,
        label: String
    ) {
        let identifiedTab = element(identifier)
        if identifiedTab.waitForExistence(timeout: 1) {
            identifiedTab.tap()
            return
        }

        let labeledTab = app.tabBars.buttons[label]
        XCTAssertTrue(
            labeledTab.waitForExistence(timeout: 3),
            "Missing tab \(label) (\(identifier))"
        )
        labeledTab.tap()
    }

    private func waitForValue(
        _ value: String,
        of element: XCUIElement,
        timeout: TimeInterval = 2
    ) {
        let expectation = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "value == %@", value),
            object: element
        )
        XCTAssertEqual(XCTWaiter.wait(for: [expectation], timeout: timeout), .completed)
    }

    private func waitForHittable(
        _ element: XCUIElement,
        timeout: TimeInterval = 3
    ) {
        let expectation = XCTNSPredicateExpectation(
            predicate: NSPredicate(format: "hittable == true"),
            object: element
        )
        XCTAssertEqual(XCTWaiter.wait(for: [expectation], timeout: timeout), .completed)
    }

    private func auditCurrentScreen() throws {
        try app.performAccessibilityAudit { issue in
            let isKnownSystemSectionHeaderIssue = issue.auditType == .contrast
                && issue.compactDescription == "Contrast nearly passed"
                && (
                    issue.element == nil
                        || issue.element.map {
                            Self.knownSystemSectionHeaderLabels.contains($0.label)
                        } == true
                )
            let isKnownSwiftUIDynamicTypeIssue = issue.auditType == .dynamicType
                && issue.detailedDescription.contains("SwiftUI.AccessibilityNode")
            let tabBar = self.app.tabBars.firstMatch
            let isCoveredBySystemTabBar = issue.auditType == .contrast
                && issue.element.map {
                    tabBar.exists
                        && $0.frame.intersects(tabBar.frame)
                        && !$0.isHittable
                } == true
            let navigationBar = self.app.navigationBars.firstMatch
            let isCoveredBySystemNavigationBar = issue.element.map {
                navigationBar.exists
                    && $0.frame.intersects(navigationBar.frame)
            } == true
            let isUnmappedOffscreenSettingsIssue =
                issue.compactDescription == "Text clipped"
                    && issue.element == nil
                    && self.element("screen.settings").exists
            let isKnownToolIssue =
                isKnownSystemSectionHeaderIssue
                    || isKnownSwiftUIDynamicTypeIssue
                    || isCoveredBySystemTabBar
                    || isCoveredBySystemNavigationBar
                    || isUnmappedOffscreenSettingsIssue

            if !isKnownToolIssue {
                XCTContext.runActivity(
                    named: "Accessibility audit: \(issue.compactDescription) [\(issue.element?.label ?? "unknown element")]"
                ) { activity in
                    let attachment = XCTAttachment(string: issue.detailedDescription)
                    attachment.name = "Accessibility audit details"
                    attachment.lifetime = .keepAlways
                    activity.add(attachment)

                    let hierarchy = XCTAttachment(string: self.app.debugDescription)
                    hierarchy.name = "Accessibility hierarchy"
                    hierarchy.lifetime = .keepAlways
                    activity.add(hierarchy)
                }
            }
            return isKnownToolIssue
        }
    }

    private static let activeRunID = "018f0d8a-8c0a-7000-8000-000000000001"
    private static let failedRunID = "018f0d8a-8c0a-7000-8000-000000000002"
    private static let pairingURL =
        "runbuoy://pair/session_ui_test?challenge=once-only&machine=UI%20Test%20Mac&platform=macOS&region=global"
    private static let knownSystemSectionHeaderLabels: Set<String> = [
        "Active Runs",
        "Timing",
        "Safe Message",
        "Run Feed",
        "Uploaded Safe Log Snippet",
        "Run ID",
        "Recent Runs",
        "Recent Messages",
        "Connections",
        "Notifications and Display",
        "Storage",
        "Identity and Data",
        "About"
    ]
}
