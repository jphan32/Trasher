// 코디네이터 ↔ SwiftUI 브리지. SessionCoordinator(@MainActor)의 상태를 @Published로 노출.
import Foundation
import SwiftUI
import TrasherCore
#if canImport(UIKit)
import UIKit
#endif

@MainActor
final class AppModel: ObservableObject {
    @Published private(set) var model: ScreenModel
    @Published var drawnSeed: Seed?
    @Published private(set) var photo: UIImage?   // 투입된 쓰레기 사진(processing/reward 표시)

    private let coordinator: SessionCoordinator
    private let central = BLECentral()
    private let seedReward = SeedReward()
    private var heartbeatTask: Task<Void, Never>?

    init() {
        let central = self.central
        coordinator = SessionCoordinator(
            link: central,
            fetcher: URLSessionPhotoFetcher(),
            classifier: MockClassificationService()  // 실제 API 확정 시 교체
        )
        model = screenModel(for: .disconnected)
        central.coordinator = coordinator
        coordinator.onStateChange = { [weak self] state in
            self?.apply(state)
        }
        coordinator.onPhotoData = { [weak self] data in
            self?.photo = UIImage(data: data)
        }
        central.start()
        // weak self 반복 Task — self 해제 시 자동 종료(별도 deinit 정리 불필요).
        heartbeatTask = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 1_000_000_000)
                guard let self else { return }
                self.coordinator.checkHeartbeat()
            }
        }
    }

    private func apply(_ state: SessionCoordinator.SessionState) {
        model = screenModel(for: state)
        if case .reward = state {} else { drawnSeed = nil }  // 보상 화면 떠날 때 초기화
        switch state {                                        // 대기/연결끊김 복귀 시 사진 초기화
        case .attract, .disconnected: photo = nil
        default: break
        }
    }

    // 씨앗 추첨(reward 화면에서 호출)
    func drawSeed() {
        drawnSeed = seedReward.draw()
    }

    // 씨앗 받기 완료 → 어트랙트 복귀 + 감지 재개(§2.1)
    func finishSeed() {
        drawnSeed = nil
        coordinator.seedInteractionFinished()
    }

    // 운영자(정비) 명령
    func operatorCommand(_ type: CommandType, arg: String? = nil) {
        coordinator.sendOperatorCommand(type, arg: arg)
    }

    // 포그라운드 복귀 시 스캔 재개(전시 무인운영). 이미 연결돼 있으면 no-op.
    func resumeScanning() {
        central.start()
    }

    let seeds: [Seed] = SeedReward().seeds
}
