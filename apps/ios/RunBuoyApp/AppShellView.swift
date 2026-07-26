import SwiftUI

struct AppShellView: View {
    @Environment(AppRouter.self) private var router

    var body: some View {
        @Bindable var router = router
        TabView(selection: $router.selectedTab) {
            NavigationStack(path: $router.runsPath) {
                RunsView()
                    .withAppDestinations()
            }
            .tabItem {
                Label("tab.runs", systemImage: "waveform.path.ecg")
            }
            .tag(AppTab.runs)

            NavigationStack(path: $router.settingsPath) {
                SettingsView()
                    .withAppDestinations()
            }
            .tabItem {
                Label("tab.settings", systemImage: "gearshape")
            }
            .tag(AppTab.settings)
        }
    }
}

private extension View {
    func withAppDestinations() -> some View {
        navigationDestination(for: AppRoute.self) { route in
            switch route {
            case .runDetail(let id):
                RunDetailView(runID: id)
            case .machines:
                MachinesView()
            case .machine(let id):
                MachineDetailView(machineID: id)
            case .pairMachine:
                PairMachineView()
            }
        }
    }
}

#Preview {
    AppShellView()
        .environment(PreviewFixtures.store())
        .environment(AppRouter())
}
