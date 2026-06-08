// SessionCoordinator 통합 테스트 — 전부 mock. docs/protocol.md §2.1, §2.2, §6.
import XCTest
@testable import TrasherCore

private final class FakeClock: @unchecked Sendable {
    var now = Date(timeIntervalSince1970: 1000)
    func advance(_ s: TimeInterval) { now += s }
}

private struct OKFetcher: PhotoFetcher {
    let data: Data
    func fetch(_ photo: PhotoReady, from device: DeviceInfo) async throws -> Data { data }
}

private struct FailFetcher: PhotoFetcher {
    func fetch(_ photo: PhotoReady, from device: DeviceInfo) async throws -> Data {
        throw PhotoFetchError.badURL
    }
}

private struct SlowFetcher: PhotoFetcher {
    func fetch(_ photo: PhotoReady, from device: DeviceInfo) async throws -> Data {
        try await Task.sleep(nanoseconds: 1_000_000_000)  // deadline보다 김
        return Data()
    }
}

private struct ThrowingClassifier: ClassificationService {
    func classify(imageData: Data) async throws -> RawClassification {
        throw PhotoFetchError.badURL
    }
}

@MainActor
final class SessionCoordinatorTests: XCTestCase {
    private let device = DeviceInfo(fw: "0.1.0", ip: "127.0.0.1", port: 8080)

    private func make(
        fetcher: PhotoFetcher = OKFetcher(data: Data([0xFF, 0xD8])),
        label: String = "pet",
        confidence: Double = 0.95,
        clock: FakeClock = FakeClock(),
        resultDeadline: TimeInterval = 12.0
    ) -> (SessionCoordinator, MockPeripheralLink, FakeClock) {
        let link = MockPeripheralLink()
        let c = SessionCoordinator(
            link: link,
            fetcher: fetcher,
            classifier: MockClassificationService(label: label, confidence: confidence),
            normalizer: CategoryNormalizer(),
            clock: { clock.now },
            resultDeadline: resultDeadline
        )
        return (c, link, clock)
    }

    func testConnectSendsStartAndAttract() {
        let (c, link, _) = make()
        c.connected(device)
        XCTAssertEqual(c.state, .attract)
        XCTAssertEqual(link.lastCommand?.cmd, .start)  // §2.1
    }

    func testIncompatibleProtoBlocks() {
        let (c, link, _) = make()
        c.connected(DeviceInfo(fw: "x", ip: "1.2.3.4", port: 8080, name: "s", proto: 2))
        XCTAssertEqual(c.state, .incompatible(proto: 2))
        XCTAssertTrue(link.commands.isEmpty)  // start 안 보냄
    }

    func testFullCycleReward() async {
        let (c, link, _) = make(label: "pet", confidence: 0.95)
        c.connected(device)
        c.received(Status(state: .detecting, cycle: 1, seq: 1))
        XCTAssertEqual(c.state, .processing(.detecting))

        await c.received(PhotoReady(cycle: 1, path: "/photos/1.jpg"))
        XCTAssertEqual(link.lastResult?.category, .pet)
        XCTAssertEqual(link.lastResult?.cycle, 1)

        c.received(Status(state: .sorting, cycle: 1, seq: 2, lastSort: .pet))
        XCTAssertEqual(c.state, .processing(.sorting))
        c.received(Status(state: .idle, cycle: 1, seq: 3, lastSort: .pet))  // sort 완료
        XCTAssertEqual(c.state, .reward(.pet))
        XCTAssertEqual(link.lastCommand?.cmd, .stop)  // §2.1 게이팅

        c.seedInteractionFinished()
        XCTAssertEqual(c.state, .attract)
        XCTAssertEqual(link.lastCommand?.cmd, .start)  // 감지 재개
    }

    func testRewardStaysDuringIdleHeartbeats() async {
        let (c, _, _) = make()
        c.connected(device)
        await c.received(PhotoReady(cycle: 1, path: "/p/1.jpg"))  // activeCycle=1
        c.received(Status(state: .sorting, cycle: 1, seq: 1, lastSort: .can))
        c.received(Status(state: .idle, cycle: 1, seq: 2, lastSort: .can))
        XCTAssertEqual(c.state, .reward(.can))
        c.received(Status(state: .idle, cycle: 1, seq: 3, lastSort: .can))  // 하트비트
        XCTAssertEqual(c.state, .reward(.can))  // 어트랙트로 되돌아가지 않음
    }

    func testGatingStopSentOnSortingEntry() async {
        let (c, link, _) = make()
        c.connected(device)
        await c.received(PhotoReady(cycle: 1, path: "/p/1.jpg"))  // activeCycle=1
        let before = link.commands.filter { $0.cmd == .stop }.count
        c.received(Status(state: .sorting, cycle: 1, seq: 2, lastSort: .pet))
        XCTAssertEqual(link.commands.filter { $0.cmd == .stop }.count, before + 1)  // 진입 시 1회
        c.received(Status(state: .sorting, cycle: 1, seq: 3, lastSort: .pet))  // 중복 stop 안 보냄
        XCTAssertEqual(link.commands.filter { $0.cmd == .stop }.count, before + 1)
    }

    func testCycleMismatchDoesNotReward() async {
        let (c, _, _) = make()
        c.connected(device)
        await c.received(PhotoReady(cycle: 1, path: "/p/1.jpg"))  // activeCycle=1
        c.received(Status(state: .sorting, cycle: 2, seq: 2, lastSort: .pet))  // 다른 cycle
        c.received(Status(state: .idle, cycle: 2, seq: 3, lastSort: .pet))
        if case .reward = c.state { XCTFail("cycle 불일치인데 reward로 감") }
    }

    func testResultDeadlineFallsBackToTimeout() async {
        let (c, link, _) = make(fetcher: SlowFetcher(), resultDeadline: 0.05)
        c.connected(device)
        await c.received(PhotoReady(cycle: 8, path: "/p/8.jpg"))
        XCTAssertEqual(link.lastResult?.category, .other)  // §6 deadline 폴백
        XCTAssertEqual(link.lastResult?.raw, "timeout")
        XCTAssertEqual(link.lastResult?.cycle, 8)
    }

    func testIncompatibleStickyIgnoresTraffic() async {
        let (c, link, _) = make()
        c.connected(DeviceInfo(fw: "x", ip: "1.2.3.4", port: 8080, name: "s", proto: 2))
        XCTAssertEqual(c.state, .incompatible(proto: 2))
        c.received(Status(state: .idle, cycle: 0, seq: 1))
        XCTAssertEqual(c.state, .incompatible(proto: 2))  // 덮어쓰지 않음
        await c.received(PhotoReady(cycle: 1, path: "/p/1.jpg"))
        XCTAssertNil(link.lastResult)  // photo 무시
    }

    func testReconciliationFollowsPiLastSort() async {
        // 우리는 pet으로 분류했지만 Pi가 타임아웃으로 other 처리 → reward(.other)
        let (c, link, _) = make(label: "pet", confidence: 0.95)
        c.connected(device)
        await c.received(PhotoReady(cycle: 1, path: "/p/1.jpg"))
        XCTAssertEqual(link.lastResult?.category, .pet)
        c.received(Status(state: .sorting, cycle: 1, seq: 2, err: .resultTimeout, lastSort: .other))
        c.received(Status(state: .idle, cycle: 1, seq: 3, lastSort: .other))
        XCTAssertEqual(c.state, .reward(.other))  // §2.2 Pi 진실을 따름
    }

    func testFetchFailureSendsOtherFallback() async {
        let (c, link, _) = make(fetcher: FailFetcher())
        c.connected(device)
        await c.received(PhotoReady(cycle: 5, path: "/p/5.jpg"))
        XCTAssertEqual(link.lastResult?.category, .other)  // §6 폴백
        XCTAssertEqual(link.lastResult?.cycle, 5)
        XCTAssertEqual(link.lastResult?.confidence, 0)
    }

    func testLowConfidenceNormalizedToOther() async {
        let (c, link, _) = make(label: "pet", confidence: 0.2)  // 임계값 미만
        c.connected(device)
        await c.received(PhotoReady(cycle: 3, path: "/p/3.jpg"))
        XCTAssertEqual(link.lastResult?.category, .other)
    }

    func testErrorAndMaintenanceStates() {
        let (c, _, _) = make()
        c.connected(device)
        c.received(Status(state: .error, cycle: 0, seq: 1, err: .cameraFail))
        XCTAssertEqual(c.state, .error(.cameraFail))
        c.received(Status(state: .maintenance, cycle: 0, seq: 2))
        XCTAssertEqual(c.state, .maintenance)
    }

    func testHeartbeatStallAndRecovery() {
        let (c, _, clock) = make()
        c.connected(device)
        c.received(Status(state: .idle, cycle: 0, seq: 1))
        clock.advance(7)  // stallThreshold(6) 초과
        c.checkHeartbeat()
        XCTAssertEqual(c.state, .stalled)
        c.received(Status(state: .idle, cycle: 0, seq: 2))  // 새 seq → 회복
        XCTAssertEqual(c.state, .attract)
    }

    func testDisconnect() {
        let (c, _, _) = make()
        c.connected(device)
        c.disconnected()
        XCTAssertEqual(c.state, .disconnected)
    }

    func testOperatorCommandPassthrough() {
        let (c, link, _) = make()
        c.connected(device)
        c.sendOperatorCommand(.estop)
        XCTAssertEqual(link.lastCommand?.cmd, .estop)
    }

    func testPhotoShownEvenWhenClassifyFails() async {
        let link = MockPeripheralLink()
        let clock = FakeClock()
        let c = SessionCoordinator(
            link: link, fetcher: OKFetcher(data: Data([1, 2, 3])),
            classifier: ThrowingClassifier(), clock: { clock.now }
        )
        var shown: Data?
        c.onPhotoData = { shown = $0 }
        c.connected(device)
        await c.received(PhotoReady(cycle: 1, path: "/p/1.jpg"))
        XCTAssertEqual(shown, Data([1, 2, 3]))            // 분류 실패해도 사진은 표시됨
        XCTAssertEqual(link.lastResult?.category, .other)  // §6 폴백 결과는 여전히 전송
    }

    func testRewardWithoutObservingSortingEdge() async {
        // sorting notify가 드롭된 경우: idle + cycle + lastSort 만으로 reward를 복구해야 함.
        let (c, link, _) = make()
        c.connected(device)
        await c.received(PhotoReady(cycle: 1, path: "/p/1.jpg"))  // activeCycle=1
        c.received(Status(state: .idle, cycle: 1, seq: 5, lastSort: .pet))  // sorting 건너뜀
        XCTAssertEqual(c.state, .reward(.pet))
        XCTAssertEqual(link.lastCommand?.cmd, .stop)  // reward 진입 게이팅 fallback
    }

    func testIdleWithoutLastSortDoesNotReward() async {
        // 중단된 cycle: Pi가 lastSort를 클리어 → idle+cycle 일치여도 reward 아님(오인 방지).
        let (c, _, _) = make()
        c.connected(device)
        await c.received(PhotoReady(cycle: 2, path: "/p/2.jpg"))  // activeCycle=2
        c.received(Status(state: .idle, cycle: 2, seq: 9))  // lastSort 없음(중단됨)
        if case .reward = c.state { XCTFail("lastSort 없는데 reward로 감") }
    }

    func testStallDoesNotClobberReward() async {
        let (c, _, clock) = make()
        c.connected(device)
        await c.received(PhotoReady(cycle: 1, path: "/p/1.jpg"))
        c.received(Status(state: .idle, cycle: 1, seq: 1, lastSort: .can))
        XCTAssertEqual(c.state, .reward(.can))
        clock.advance(10)
        c.checkHeartbeat()  // 보상/씨앗 중에는 stall로 덮지 않음
        XCTAssertEqual(c.state, .reward(.can))
    }
}
