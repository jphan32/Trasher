// 데모 모드 — Pi 없이 전체 사이클을 자동 시연(하드웨어 대기 중 시연/QA).
// DemoDriver가 "가짜 Pi" 역할: PeripheralLink를 구현하고 코디네이터에 Status/PhotoReady를 주입한다.
import Foundation
import SwiftUI
import TrasherCore
#if canImport(UIKit)
import UIKit
#endif

/// 합성 트래시 사진(번들 에셋 불필요). 데모/프리뷰용.
struct SampleImageFetcher: PhotoFetcher {
    func fetch(_ photo: PhotoReady, from device: DeviceInfo) async throws -> Data {
        #if canImport(UIKit)
        let size = CGSize(width: 300, height: 300)
        let image = UIGraphicsImageRenderer(size: size).image { ctx in
            // 합성 "사진" — 촬영물은 밝은 배경이 자연스러워 다크 UI와 별개로 라이트 톤 유지.
            UIColor(white: 0.93, alpha: 1).setFill()
            ctx.fill(CGRect(origin: .zero, size: size))
            UIColor(Theme.sprout).setFill()
            ctx.cgContext.fillEllipse(in: CGRect(x: 75, y: 75, width: 150, height: 150))
        }
        return image.pngData() ?? Data()
        #else
        return Data()
        #endif
    }
}

/// 데모용 분류기 — 4가지를 팁·에코포인트와 함께 회전(보상 티어 2/2/1/0 시연).
/// pet/can(재활용·고점수), other-유리(재활용·중점수), other-일반쓰레기(비재활용·0점).
final class DemoClassifier: ClassificationService, @unchecked Sendable {
    private let lock = NSLock()
    private var index = 0
    // (category, tip, ecoPoints, recyclable)
    private let items: [(String, String, Int, Bool)] = [
        ("pet", "페트병은 라벨을 떼고 내용물을 비운 뒤 압착해 투명 페트 전용함에 배출해요.", 60, true),
        ("can", "캔은 내용물을 비우고 물로 헹군 뒤 납작하게 만들어 캔류로 배출해요.", 55, true),
        ("other", "유리병은 색깔별로 모아 유리류 전용함에 배출하면 재활용돼요.", 30, true),
        ("other", "재활용이 어려운 일반 쓰레기는 종량제 봉투에 배출해요.", 0, false),
    ]
    func classify(cycle: Int, on device: DeviceInfo) async throws -> RawClassification {
        let item = lock.withLock { () -> (String, String, Int, Bool) in
            let picked = items[index % items.count]
            index += 1
            return picked
        }
        return RawClassification(
            label: item.0, confidence: 0.95, description: item.1,
            ecoPoints: item.2, recyclable: item.3
        )
    }
}

@MainActor
final class DemoDriver: PeripheralLink {
    weak var coordinator: SessionCoordinator?
    private var seq = 0
    private var cycle = 0
    private var task: Task<Void, Never>?

    // 코디네이터의 아웃바운드 — 데모는 자동 루프라 무시(no-op). nonisolated로 프로토콜 요구 충족.
    // iPad가 보낸 분류 결과를 가짜 Pi의 sort 카테고리로 사용(reward 카테고리=분류=팁 일치).
    nonisolated(unsafe) private var pendingCategory: WasteCategory = .other
    nonisolated func writeResult(_ result: ClassificationResult) { pendingCategory = result.category }
    nonisolated func writeCommand(_ command: Command) {}

    func start() {
        coordinator?.connected(DeviceInfo(fw: "demo", ip: "0.0.0.0", port: 0))
        task = Task { @MainActor in await loop() }
    }

    func stop() { task?.cancel() }

    private func loop() async {
        while !Task.isCancelled {
            await sleep(2.5)                                  // 어트랙트
            cycle += 1
            emit(.detecting); await sleep(0.9)
            emit(.capturing); await sleep(0.6)
            emit(.awaitingResult); await sleep(0.3)          // AI 인식 단계
            // iPad가 사진을 받아 분류(DemoClassifier 회전) → writeResult로 pendingCategory 설정
            await coordinator?.received(PhotoReady(cycle: cycle, path: "/photos/\(cycle).jpg"))
            await sleep(0.8)
            let category = pendingCategory                   // 분류 결과대로 sort(카테고리=팁 일치)
            emit(.sorting, lastSort: category); await sleep(1.3)
            emit(.idle, lastSort: category)                  // reward 진입
            // 보상 자동복귀는 RewardView.startAutoSequence가 소유(실/데모 일관, 당첨~11s/미당첨~8s).
            // 데모는 최대 시퀀스보다 길게 대기해 끊김 없이 다음 사이클로 넘어간다(trash-iwg).
            await sleep(12.0)
        }
    }

    private func emit(_ state: PiState, lastSort: WasteCategory? = nil) {
        seq += 1
        coordinator?.received(Status(state: state, cycle: cycle, seq: seq, lastSort: lastSort))
    }

    private func sleep(_ seconds: Double) async {
        try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
    }
}
