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
    @Published private(set) var ecoReward: EcoReward?  // 에코포인트→막대사탕 보상(reward 표시, §4.6)
    @Published private(set) var photo: UIImage?   // 투입된 쓰레기 사진(processing/reward 표시)
    @Published private(set) var tip: String?      // 재활용 팁(reward 부가정보)
    @Published private(set) var step: CycleStep?  // 현재 처리 단계(촬영→AI인식→이동→분류)
    @Published private(set) var stats: SortStats   // 누적 분류 집계(어트랙트 표시)

    private static let statsKey = "trasher.sortStats"

    private let coordinator: SessionCoordinator
    private let central: BLECentral?      // 데모 모드에서는 nil
    private let demo: DemoDriver?          // 실 모드에서는 nil
    private var heartbeatTask: Task<Void, Never>?

    /// demo=true(또는 --demo / TRASHER_DEMO=1)면 Pi 없이 자동 사이클 시연.
    init(demo demoRequested: Bool = false) {
        let env = ProcessInfo.processInfo
        let useDemo = demoRequested
            || env.arguments.contains("--demo")
            || env.environment["TRASHER_DEMO"] == "1"

        model = screenModel(for: .disconnected)
        stats = Self.loadStats()

        if useDemo {
            let driver = DemoDriver()
            coordinator = SessionCoordinator(
                link: driver,
                fetcher: SampleImageFetcher(),
                classifier: DemoClassifier()  // 카테고리·팁 회전(데모 일관)
            )
            demo = driver
            central = nil
        } else {
            let ble = BLECentral()
            coordinator = SessionCoordinator(
                link: ble,
                fetcher: URLSessionPhotoFetcher(),
                classifier: PiClassificationService()  // Pi /classify/{cycle} 호출(주소=DeviceInfo)
            )
            central = ble
            demo = nil
        }

        coordinator.onStateChange = { [weak self] state in self?.apply(state) }
        coordinator.onPhotoData = { [weak self] data in self?.photo = UIImage(data: data) }
        coordinator.onCycleComplete = { [weak self] category in self?.recordSort(category) }
        coordinator.onTip = { [weak self] tip in self?.tip = tip }
        coordinator.onEcoReward = { [weak self] reward in self?.ecoReward = reward }

        central?.coordinator = coordinator
        demo?.coordinator = coordinator
        central?.start()
        demo?.start()

        // weak self 반복 Task — self 해제 시 루프가 자동 종료된다(다음 tick에서). deinit에서
        // 즉시 취소해 잔여 sleep(최대 1초) 없이 정리한다.
        heartbeatTask = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 1_000_000_000)
                guard let self else { return }
                self.coordinator.checkHeartbeat()
            }
        }
    }

    deinit {
        heartbeatTask?.cancel()
    }

    private func apply(_ state: SessionCoordinator.SessionState) {
        model = screenModel(for: state)
        step = cycleStep(for: state)  // 진행 스테퍼 단계
        // ecoReward는 분류 직후(processing 중) 세팅되어 reward 화면까지 유지되어야 한다.
        // 따라서 사진·팁과 동일하게 사이클 종료(어트랙트/연결끊김) 시에만 초기화한다.
        // (reward 직전 sorting 상태에서 지우면 보상이 0으로 표시되는 회귀 — 주의)
        switch state {
        case .attract, .disconnected:
            photo = nil
            tip = nil
            ecoReward = nil
        default: break
        }
    }

    // 보상 수령 완료 → 어트랙트 복귀 + 감지 재개(§2.1)
    func finishReward() {
        ecoReward = nil
        coordinator.rewardFinished()
    }

    // 운영자(정비) 명령
    func operatorCommand(_ type: CommandType, arg: String? = nil) {
        coordinator.sendOperatorCommand(type, arg: arg)
    }

    // 포그라운드 복귀 시 스캔 재개(전시 무인운영). 이미 연결돼 있으면 no-op. 데모 모드는 no-op.
    func resumeScanning() {
        central?.start()
    }

    // MARK: 누적 집계 영속(UserDefaults)
    private func recordSort(_ category: WasteCategory) {
        stats.record(category)
        persistStats()
    }

    /// 운영자: 누적 통계 리셋.
    func resetStats() {
        stats = SortStats()
        persistStats()
    }

    private func persistStats() {
        if let data = try? JSONEncoder().encode(stats) {
            UserDefaults.standard.set(data, forKey: Self.statsKey)
        }
    }

    private static func loadStats() -> SortStats {
        guard let data = UserDefaults.standard.data(forKey: statsKey),
              let s = try? JSONDecoder().decode(SortStats.self, from: data) else {
            return SortStats()
        }
        return s
    }
}
