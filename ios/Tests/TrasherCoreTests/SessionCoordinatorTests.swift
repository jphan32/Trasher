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

@MainActor
final class SessionCoordinatorTests: XCTestCase {
    private let device = DeviceInfo(fw: "0.1.0", ip: "127.0.0.1", port: 8080)

    private func make(
        fetcher: PhotoFetcher = OKFetcher(data: Data([0xFF, 0xD8])),
        label: String = "pet",
        confidence: Double = 0.95,
        clock: FakeClock = FakeClock()
    ) -> (SessionCoordinator, MockPeripheralLink, FakeClock) {
        let link = MockPeripheralLink()
        let c = SessionCoordinator(
            link: link,
            fetcher: fetcher,
            classifier: MockClassificationService(label: label, confidence: confidence),
            normalizer: CategoryNormalizer(),
            clock: { clock.now }
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

    func testRewardStaysDuringIdleHeartbeats() {
        let (c, _, _) = make()
        c.connected(device)
        c.received(Status(state: .sorting, cycle: 1, seq: 1, lastSort: .can))
        c.received(Status(state: .idle, cycle: 1, seq: 2, lastSort: .can))
        XCTAssertEqual(c.state, .reward(.can))
        c.received(Status(state: .idle, cycle: 1, seq: 3, lastSort: .can))  // 하트비트
        XCTAssertEqual(c.state, .reward(.can))  // 어트랙트로 되돌아가지 않음
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
}
