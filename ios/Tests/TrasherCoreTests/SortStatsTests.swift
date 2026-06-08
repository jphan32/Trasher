// 분류 누적 집계 테스트 — 카운트/직렬화 + 코디네이터 사이클당 1회 증가.
import XCTest
@testable import TrasherCore

final class SortStatsTests: XCTestCase {
    func testRecordAndTotal() {
        var s = SortStats()
        s.record(.pet); s.record(.pet); s.record(.can)
        XCTAssertEqual(s.count(.pet), 2)
        XCTAssertEqual(s.count(.can), 1)
        XCTAssertEqual(s.count(.other), 0)
        XCTAssertEqual(s.total, 3)
    }

    func testCodableRoundtrip() throws {
        let s = SortStats().recording(.pet).recording(.other)
        let data = try JSONEncoder().encode(s)
        let decoded = try JSONDecoder().decode(SortStats.self, from: data)
        XCTAssertEqual(decoded, s)
        XCTAssertEqual(decoded.count(.pet), 1)
        XCTAssertEqual(decoded.count(.other), 1)
    }
}

@MainActor
final class CoordinatorStatsTests: XCTestCase {
    private let device = DeviceInfo(fw: "0.1.0", ip: "127.0.0.1", port: 8080)

    func testCycleCompleteFiresOncePerCycle() async {
        let link = MockPeripheralLink()
        let c = SessionCoordinator(
            link: link, fetcher: MockFetcher(), classifier: MockClassificationService()
        )
        var completed: [WasteCategory] = []
        c.onCycleComplete = { completed.append($0) }
        c.connected(device)
        await c.received(PhotoReady(cycle: 1, path: "/p/1.jpg"))  // activeCycle=1
        c.received(Status(state: .sorting, cycle: 1, seq: 1, lastSort: .can))
        c.received(Status(state: .idle, cycle: 1, seq: 2, lastSort: .can))      // reward 진입
        c.received(Status(state: .idle, cycle: 1, seq: 3, lastSort: .can))      // 하트비트
        XCTAssertEqual(completed, [.can])  // 사이클당 정확히 1회(하트비트 중복 없음)
    }
}

private struct MockFetcher: PhotoFetcher {
    func fetch(_ photo: PhotoReady, from device: DeviceInfo) async throws -> Data { Data([0xFF, 0xD8]) }
}
