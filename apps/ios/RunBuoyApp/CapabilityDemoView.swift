import ActivityKit
import Observation
import SwiftUI
import UIKit
import UserNotifications

enum CapabilityDemoStep: Int, CaseIterable, Identifiable {
    case starting = 1
    case indeterminate
    case progress
    case warning
    case stale
    case succeeded
    case failed

    var id: Int { rawValue }

    var title: LocalizedStringKey {
        switch self {
        case .starting: "demo.step.starting"
        case .indeterminate: "demo.step.indeterminate"
        case .progress: "demo.step.progress"
        case .warning: "demo.step.warning"
        case .stale: "demo.step.stale"
        case .succeeded: "demo.step.succeeded"
        case .failed: "demo.step.failed"
        }
    }

    var explanation: LocalizedStringKey {
        switch self {
        case .starting: "demo.step.starting_explanation"
        case .indeterminate: "demo.step.indeterminate_explanation"
        case .progress: "demo.step.progress_explanation"
        case .warning: "demo.step.warning_explanation"
        case .stale: "demo.step.stale_explanation"
        case .succeeded: "demo.step.succeeded_explanation"
        case .failed: "demo.step.failed_explanation"
        }
    }

    var symbol: String {
        switch self {
        case .starting: "hourglass"
        case .indeterminate: "ellipsis.circle"
        case .progress: "chart.bar.fill"
        case .warning: "exclamationmark.triangle.fill"
        case .stale: "wifi.slash"
        case .succeeded: "checkmark.circle.fill"
        case .failed: "xmark.octagon.fill"
        }
    }

    var next: CapabilityDemoStep? {
        switch self {
        case .starting: .indeterminate
        case .indeterminate: .progress
        case .progress: .warning
        case .warning: .stale
        case .stale: .succeeded
        case .succeeded, .failed: nil
        }
    }

    var isTerminal: Bool {
        self == .succeeded || self == .failed
    }

    func contentState(
        now: Date,
        createdAt: Date,
        startedAt: Date
    ) -> RunActivityAttributes.ContentState {
        let progress: Double? = switch self {
        case .progress, .warning, .stale, .failed: 0.72
        case .succeeded: 1
        case .starting, .indeterminate: nil
        }
        let executionStatus: String = switch self {
        case .starting: "STARTING"
        case .succeeded: "SUCCEEDED"
        case .failed: "FAILED"
        default: "RUNNING"
        }
        let healthStatus = self == .stale ? "STALE" : "HEALTHY"
        let attentionStatus = self == .warning ? "WARNING" : "NONE"

        return RunActivityAttributes.ContentState(
            sequence: rawValue,
            executionStatus: executionStatus,
            healthStatus: healthStatus,
            attentionStatus: attentionStatus,
            progressKind: progress == nil ? "indeterminate" : "determinate",
            progress: progress,
            current: progress.map { $0 * 100 },
            total: progress == nil ? nil : 100,
            phase: phaseText,
            message: messageText,
            createdAt: createdAt,
            startedAt: startedAt,
            updatedAt: now,
            machineName: String(localized: "demo.local_machine"),
            endedAt: isTerminal ? now : nil,
            estimatedEndAt: progress != nil && !isTerminal
                ? now.addingTimeInterval(240)
                : nil,
            exitCode: self == .failed ? 1 : nil
        )
    }

    static func step(for state: RunActivityAttributes.ContentState) -> CapabilityDemoStep {
        switch state.executionStatus {
        case "SUCCEEDED": return .succeeded
        case "FAILED": return .failed
        case "STARTING": return .starting
        default: break
        }
        if state.healthStatus == "STALE" || state.healthStatus == "OFFLINE" {
            return .stale
        }
        if state.attentionStatus == "WARNING" || state.attentionStatus == "ACTION_REQUIRED" {
            return .warning
        }
        if state.progressKind == "determinate", state.progress != nil {
            return .progress
        }
        return .indeterminate
    }

    private var phaseText: String {
        switch self {
        case .starting: String(localized: "demo.phase.starting")
        case .indeterminate: String(localized: "demo.phase.preparing")
        case .progress: String(localized: "demo.phase.processing")
        case .warning: String(localized: "demo.phase.checking")
        case .stale: String(localized: "demo.phase.waiting")
        case .succeeded: String(localized: "demo.phase.completed")
        case .failed: String(localized: "demo.phase.failed")
        }
    }

    private var messageText: String? {
        switch self {
        case .warning: String(localized: "demo.message.warning")
        case .stale: String(localized: "demo.message.stale")
        case .succeeded: String(localized: "demo.message.succeeded")
        case .failed: String(localized: "demo.message.failed")
        default: nil
        }
    }
}

enum DemoNotificationPermission: Equatable {
    case unknown
    case available
    case disabled

    var title: LocalizedStringKey {
        switch self {
        case .unknown: "demo.status.not_requested"
        case .available: "demo.status.available"
        case .disabled: "demo.status.disabled"
        }
    }
}

@MainActor
@Observable
final class CapabilityDemoModel {
    enum SessionState: Equatable {
        case idle
        case active(CapabilityDemoStep)
        case ended(CapabilityDemoStep)
    }

    private(set) var sessionState: SessionState = .idle
    private(set) var liveActivitiesAvailable = false
    private(set) var notificationPermission: DemoNotificationPermission = .unknown
    private(set) var isWorking = false
    private(set) var issueMessage: String?
    private(set) var notificationMessage: String?
    private var activityID: String?

    func refresh() async {
        liveActivitiesAvailable = ActivityAuthorizationInfo().areActivitiesEnabled
        await refreshNotificationPermission()

        let demoActivities = Activity<RunActivityAttributes>.activities.filter {
            $0.attributes.isDemo
        }
        guard let current = demoActivities.max(by: {
            $0.content.state.updatedAt < $1.content.state.updatedAt
        }) else {
            if case .active = sessionState {
                sessionState = .idle
                activityID = nil
            }
            return
        }

        for duplicate in demoActivities where duplicate.id != current.id {
            await duplicate.end(nil, dismissalPolicy: .immediate)
        }
        activityID = current.id
        sessionState = .active(CapabilityDemoStep.step(for: current.content.state))
    }

    func start() async {
        liveActivitiesAvailable = ActivityAuthorizationInfo().areActivitiesEnabled
        guard liveActivitiesAvailable else {
            issueMessage = String(localized: "demo.error.live_activities_disabled")
            return
        }

        isWorking = true
        issueMessage = nil
        defer { isWorking = false }
        await removeAllDemoActivities()

        let now = Date()
        let sessionID = UUID().uuidString
        let attributes = RunActivityAttributes(
            runID: UUID().uuidString,
            title: String(localized: "demo.activity_title"),
            machineName: String(localized: "demo.local_machine"),
            demoSessionID: sessionID
        )
        let step = CapabilityDemoStep.starting
        let content = ActivityContent(
            state: step.contentState(now: now, createdAt: now, startedAt: now),
            staleDate: now.addingTimeInterval(60)
        )

        do {
            let activity = try Activity<RunActivityAttributes>.request(
                attributes: attributes,
                content: content,
                pushType: nil
            )
            activityID = activity.id
            sessionState = .active(step)
        } catch {
            issueMessage = "\(String(localized: "demo.error.start_failed")) \(error.localizedDescription)"
            sessionState = .idle
        }
    }

    func advance() async {
        guard case .active(let step) = sessionState,
              let next = step.next
        else { return }
        await setStep(next)
    }

    func setStep(_ step: CapabilityDemoStep) async {
        guard let activity = currentActivity() else {
            sessionState = .idle
            activityID = nil
            issueMessage = String(localized: "demo.error.activity_unavailable")
            return
        }

        isWorking = true
        issueMessage = nil
        defer { isWorking = false }

        let now = Date()
        let previousState = activity.content.state
        let state = step.contentState(
            now: now,
            createdAt: previousState.createdAt ?? previousState.startedAt,
            startedAt: previousState.startedAt
        )
        let content = ActivityContent(
            state: state,
            staleDate: step == .stale
                ? now.addingTimeInterval(-1)
                : step.isTerminal ? nil : now.addingTimeInterval(60)
        )

        if step.isTerminal {
            await activity.end(
                content,
                dismissalPolicy: .after(now.addingTimeInterval(60))
            )
            activityID = nil
            sessionState = .ended(step)
        } else {
            await activity.update(content)
            sessionState = .active(step)
        }
    }

    func stop() async {
        isWorking = true
        issueMessage = nil
        defer { isWorking = false }
        await removeAllDemoActivities()
        activityID = nil
        sessionState = .idle
    }

    func sendDemoNotification() async {
        notificationMessage = nil
        issueMessage = nil
        let center = UNUserNotificationCenter.current()

        do {
            let settings = await center.notificationSettings()
            let allowed: Bool
            switch settings.authorizationStatus {
            case .notDetermined:
                allowed = try await center.requestAuthorization(options: [.alert, .sound])
            case .authorized, .provisional, .ephemeral:
                allowed = true
            case .denied:
                allowed = false
            @unknown default:
                allowed = false
            }

            guard allowed else {
                notificationPermission = .disabled
                issueMessage = String(localized: "demo.error.notifications_disabled")
                return
            }

            let content = UNMutableNotificationContent()
            content.title = String(localized: "demo.notification_title")
            content.body = String(localized: "demo.notification_body")
            content.sound = .default
            content.userInfo = [
                DemoNotificationRoute.userInfoKey: DemoNotificationRoute.url.absoluteString
            ]
            let request = UNNotificationRequest(
                identifier: DemoNotificationRoute.requestIdentifier,
                content: content,
                trigger: UNTimeIntervalNotificationTrigger(timeInterval: 5, repeats: false)
            )
            center.removePendingNotificationRequests(
                withIdentifiers: [DemoNotificationRoute.requestIdentifier]
            )
            try await center.add(request)
            notificationPermission = .available
            notificationMessage = String(localized: "demo.notification_scheduled")
        } catch {
            issueMessage = "\(String(localized: "demo.error.notification_failed")) \(error.localizedDescription)"
        }
    }

    private func refreshNotificationPermission() async {
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        switch settings.authorizationStatus {
        case .authorized, .provisional, .ephemeral:
            notificationPermission = .available
        case .denied:
            notificationPermission = .disabled
        case .notDetermined:
            notificationPermission = .unknown
        @unknown default:
            notificationPermission = .unknown
        }
    }

    private func currentActivity() -> Activity<RunActivityAttributes>? {
        let activities = Activity<RunActivityAttributes>.activities
        if let activityID,
           let exact = activities.first(where: { $0.id == activityID && $0.attributes.isDemo }) {
            return exact
        }
        return activities.first(where: { $0.attributes.isDemo })
    }

    private func removeAllDemoActivities() async {
        for activity in Activity<RunActivityAttributes>.activities where activity.attributes.isDemo {
            await activity.end(nil, dismissalPolicy: .immediate)
        }
    }
}

enum DemoNotificationRoute {
    static let userInfoKey = "runbuoy_url"
    static let requestIdentifier = "runbuoy.capability-demo.notification"
    static let url = URL(string: "runbuoy://demo/notification")!
}

@MainActor
struct CapabilityDemoView: View {
    @Environment(\.openURL) private var openURL
    @Environment(\.scenePhase) private var scenePhase
    @State private var model = CapabilityDemoModel()

    var body: some View {
        Form {
            Section {
                Label {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("demo.intro_title")
                            .font(.headline)
                        Text("demo.intro_body")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                } icon: {
                    Image(systemName: "iphone.gen3.radiowaves.left.and.right")
                        .foregroundStyle(.tint)
                }
            }

            Section("demo.system_status") {
                DemoStatusRow(
                    title: "demo.live_activities",
                    symbol: "bolt.horizontal.circle",
                    status: model.liveActivitiesAvailable
                        ? "demo.status.available"
                        : "demo.status.disabled",
                    isAvailable: model.liveActivitiesAvailable
                )
                DemoStatusRow(
                    title: "demo.notifications",
                    symbol: "bell.badge",
                    status: model.notificationPermission.title,
                    isAvailable: model.notificationPermission == .available
                )
                if !model.liveActivitiesAvailable || model.notificationPermission == .disabled {
                    Button("demo.open_settings") {
                        openSystemSettings()
                    }
                    .accessibilityIdentifier("demo.openSettings")
                }
            }

            Section {
                liveActivityContent
            } header: {
                Text("demo.live_activity_section")
            } footer: {
                Text("demo.live_activity_footer")
            }

            Section {
                Button {
                    Task { await model.sendDemoNotification() }
                } label: {
                    Label("demo.send_notification", systemImage: "bell.and.waves.left.and.right")
                }
                .disabled(model.isWorking)
                .accessibilityIdentifier("demo.sendNotification")

                if let notificationMessage = model.notificationMessage {
                    Label(notificationMessage, systemImage: "checkmark.circle")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .accessibilityIdentifier("demo.notificationScheduled")
                }
            } header: {
                Text("demo.notification_section")
            } footer: {
                Text("demo.notification_footer")
            }

            Section {
                Label("demo.flow_machine", systemImage: "desktopcomputer")
                Label("demo.flow_server", systemImage: "server.rack")
                Label("demo.flow_phone", systemImage: "iphone.gen3")
            } header: {
                Text("demo.real_flow")
            } footer: {
                Text("demo.flow_footer")
            }

            if let issueMessage = model.issueMessage {
                Section {
                    Label(issueMessage, systemImage: "exclamationmark.triangle")
                        .font(.footnote)
                        .foregroundStyle(.primary)
                        .accessibilityIdentifier("demo.issue")
                }
            }
        }
        .runBuoyBottomScrollEdgeStyle()
        .navigationTitle("demo.title")
        .navigationBarTitleDisplayMode(.inline)
        .accessibilityIdentifier("screen.capabilityDemo")
        .task(id: scenePhase) {
            guard scenePhase == .active else { return }
            await model.refresh()
        }
    }

    @ViewBuilder
    private var liveActivityContent: some View {
        switch model.sessionState {
        case .idle:
            Text("demo.live_activity_intro")
                .foregroundStyle(.secondary)
            Button {
                Task { await model.start() }
            } label: {
                Label("demo.start", systemImage: "play.fill")
            }
            .disabled(model.isWorking || !model.liveActivitiesAvailable)
            .accessibilityIdentifier("demo.startLiveActivity")

        case .active(let step):
            DemoStepRow(step: step)
            if step == .progress || step == .warning || step == .stale {
                ProgressView(value: 0.72)
                    .accessibilityLabel("widget.progress")
                    .accessibilityValue(Text(0.72, format: .percent))
            }
            if step.next != nil {
                Button {
                    Task { await model.advance() }
                } label: {
                    Label("demo.next_step", systemImage: "arrow.right.circle.fill")
                }
                .disabled(model.isWorking)
                .accessibilityLabel("demo.next_step")
                .accessibilityIdentifier("demo.nextStep")
            }
            Menu {
                ForEach(CapabilityDemoStep.allCases) { candidate in
                    Button {
                        Task { await model.setStep(candidate) }
                    } label: {
                        Label(candidate.title, systemImage: candidate.symbol)
                    }
                }
            } label: {
                Label("demo.choose_state", systemImage: "slider.horizontal.3")
            }
            .disabled(model.isWorking)
            .accessibilityIdentifier("demo.chooseState")

            Button(role: .destructive) {
                Task { await model.stop() }
            } label: {
                Label("demo.stop", systemImage: "xmark.circle")
            }
            .disabled(model.isWorking)
            .accessibilityIdentifier("demo.stopLiveActivity")

        case .ended(let step):
            DemoStepRow(step: step)
            Text("demo.ended_body")
                .font(.footnote)
                .foregroundStyle(.secondary)
            Button {
                Task { await model.start() }
            } label: {
                Label("demo.start_again", systemImage: "arrow.clockwise")
            }
            .disabled(model.isWorking || !model.liveActivitiesAvailable)
            .accessibilityIdentifier("demo.startAgain")
        }

        if model.isWorking {
            ProgressView()
                .accessibilityLabel("demo.working")
        }
    }

    private func openSystemSettings() {
        guard let url = URL(string: UIApplication.openSettingsURLString) else { return }
        openURL(url)
    }
}

private struct DemoStatusRow: View {
    let title: LocalizedStringKey
    let symbol: String
    let status: LocalizedStringKey
    let isAvailable: Bool

    var body: some View {
        LabeledContent {
            Text(status)
                .foregroundStyle(isAvailable ? Color.green : Color.secondary)
        } label: {
            Label(title, systemImage: symbol)
        }
    }
}

private struct DemoStepRow: View {
    let step: CapabilityDemoStep

    var body: some View {
        Label {
            VStack(alignment: .leading, spacing: 4) {
                Text(step.title)
                    .font(.headline)
                Text(step.explanation)
                    .font(.footnote)
                    .foregroundStyle(.secondary)
            }
        } icon: {
            Image(systemName: step.symbol)
                .foregroundStyle(iconColor)
        }
        .accessibilityElement(children: .combine)
    }

    private var iconColor: Color {
        switch step {
        case .warning, .stale: .orange
        case .succeeded: .green
        case .failed: .red
        default: .blue
        }
    }
}

#Preview {
    NavigationStack {
        CapabilityDemoView()
    }
}
