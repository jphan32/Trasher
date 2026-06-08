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
            UIColor(Theme.paperDeep).setFill()
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

@MainActor
final class DemoDriver: PeripheralLink {
    weak var coordinator: SessionCoordinator?
    private var seq = 0
    private var cycle = 0
    private var task: Task<Void, Never>?
    private let categories: [WasteCategory] = [.pet, .can, .other]

    // 코디네이터의 아웃바운드 — 데모는 자동 루프라 무시(no-op). nonisolated로 프로토콜 요구 충족.
    nonisolated func writeResult(_ result: ClassificationResult) {}
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
            let category = categories[cycle % categories.count]
            emit(.detecting); await sleep(0.9)
            emit(.capturing); await sleep(0.6)
            await coordinator?.received(PhotoReady(cycle: cycle, path: "/photos/\(cycle).jpg"))
            // §2.2: reward는 Pi의 lastSort를 따른다 → 데모는 카테고리를 회전시켜 보여줌
            emit(.sorting, lastSort: category); await sleep(1.3)
            emit(.idle, lastSort: category)                  // reward 진입
            await sleep(3.5)                                 // 결과/씨앗 표시
            coordinator?.seedInteractionFinished()
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
