import SwiftUI

struct AppShellView: View {
    @Environment(AppRouter.self) private var router

    var body: some View {
        @Bindable var router = router
        TabView(selection: $router.selectedTab) {
            Tab(value: AppTab.activeRuns) {
                NavigationStack(path: $router.activeRunsPath) {
                    ActiveRunsView()
                        .withAppDestinations()
                }
            } label: {
                Label("tab.active", systemImage: "waveform.path.ecg")
                    .accessibilityIdentifier("tab.activeRuns")
            }

            Tab(value: AppTab.history) {
                NavigationStack(path: $router.historyPath) {
                    RunHistoryView()
                        .withAppDestinations()
                }
            } label: {
                Label("tab.history", systemImage: "clock.arrow.circlepath")
                    .accessibilityIdentifier("tab.history")
            }

            Tab(value: AppTab.settings) {
                NavigationStack(path: $router.settingsPath) {
                    SettingsView()
                        .withAppDestinations()
                }
            } label: {
                Label("tab.settings", systemImage: "gearshape")
                    .accessibilityIdentifier("tab.settings")
            }
        }
        .tabViewStyle(.automatic)
    }
}

private extension View {
    func withAppDestinations() -> some View {
        navigationDestination(for: AppRoute.self) { route in
            switch route {
            case .runDetail(let id):
                RunDetailView(runID: id)
            case .machine(let id):
                MachineDetailView(machineID: id)
            case .machines:
                MachinesView()
            case .pairMachine:
                PairMachineView()
            }
        }
    }
}

#Preview("Light") {
    AppShellView()
        .environment(PreviewFixtures.store())
        .environment(AppRouter())
}

#Preview("Dark · Accessibility Type") {
    AppShellView()
        .environment(PreviewFixtures.store())
        .environment(AppRouter())
        .preferredColorScheme(.dark)
        .environment(\.dynamicTypeSize, .accessibility2)
}
