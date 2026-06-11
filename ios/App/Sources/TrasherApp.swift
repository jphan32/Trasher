// 앱 진입 + 루트 라우터. ScreenModel.screen에 따라 화면 전환.
import SwiftUI
import TrasherCore
#if canImport(UIKit)
import UIKit
#endif

@main
struct TrasherApp: App {
    @StateObject private var app = AppModel()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(app)
                .statusBarHidden()
                .persistentSystemOverlays(.hidden)
                .onAppear {
                    // 키오스크: 화면 자동 잠금 비활성(전시 무인운영).
                    #if canImport(UIKit)
                    UIApplication.shared.isIdleTimerDisabled = true
                    #endif
                }
        }
        .onChange(of: scenePhase) { phase in
            if phase == .active { app.resumeScanning() }  // 포그라운드 복귀 시 재연결 시도
        }
    }
}

struct RootView: View {
    @EnvironmentObject var app: AppModel
    @State private var showOperator = false

    var body: some View {
        ZStack {
            PaperBackground()
            content
                .transition(.asymmetric(insertion: .scale(scale: 0.92).combined(with: .opacity),
                                        removal: .opacity))
                .id(app.model.screen)  // 화면 전환 애니메이션 트리거
        }
        .animation(.spring(response: 0.5, dampingFraction: 0.8), value: app.model.screen)
        // 숨김 제스처: 좌상단 3초 길게 누르면 운영자 화면
        .overlay(alignment: .topLeading) {
            Color.clear.frame(width: 120, height: 120).contentShape(Rectangle())
                .onLongPressGesture(minimumDuration: 3) { showOperator = true }
        }
        .fullScreenCover(isPresented: $showOperator) {
            OperatorView().environmentObject(app)
        }
    }

    @ViewBuilder private var content: some View {
        switch app.model.screen {
        case .connecting: StatusView(model: app.model, accent: Theme.inkSoft, symbol: "antenna.radiowaves.left.and.right")
        case .attract: AttractView(model: app.model)
        case .processing: ProcessingView(model: app.model)
        case .reward: RewardView(model: app.model)
        case .error: StatusView(model: app.model, accent: Theme.danger, symbol: "exclamationmark.triangle.fill")
        case .stalled: StatusView(model: app.model, accent: Theme.danger, symbol: "wifi.exclamationmark")
        case .maintenance: StatusView(model: app.model, accent: Theme.inkSoft, symbol: "wrench.and.screwdriver.fill")
        }
    }
}
