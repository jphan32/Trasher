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
    @Published private(set) var tip: String?      // 재활용 팁(reward 부가정보)
    @Published private(set) var stats: SortStats   // 누적 분류 집계(어트랙트 표시)

    private static let statsKey = "trasher.sortStats"

    private let coordinator: SessionCoordinator
    private let central: BLECentral?      // 데모 모드에서는 nil
    private let demo: DemoDriver?          // 실 모드에서는 nil
    private let seedReward = SeedReward()
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

        central?.coordinator = coordinator
        demo?.coordinator = coordinator
        central?.start()
        demo?.start()

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
        switch state {                                        // 대기/연결끊김 복귀 시 사진·팁 초기화
        case .attract, .disconnected:
            photo = nil
            tip = nil
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

    // 포그라운드 복귀 시 스캔 재개(전시 무인운영). 이미 연결돼 있으면 no-op. 데모 모드는 no-op.
    func resumeScanning() {
        central?.start()
    }

    var seeds: [Seed] { seedReward.seeds }  // drawSeed와 동일 인스턴스 사용(분기 방지)

    // MARK: 누적 집계 영속(UserDefaults)
    private func recordSort(_ category: WasteCategory) {
        stats.record(category)
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
