// iPad 사이클 조정자 — Pi 오케스트레이터의 iPad 대응물.
// docs/protocol.md §2.1(게이팅), §2.2(정합화), §6(폴백). 전부 mock으로 호스트 테스트 가능.
//
// 책임:
//  - 연결 시 proto 확인 → Command{start}로 감지 개시(§2.1). 불일치면 sticky 차단.
//  - Status 수신 → UI 상태 구동. sort 진입 시 stop 선제 전송(§2.1 레이스 방지),
//    sort 완료 시 같은 cycle의 lastSort를 진실로 결과 표시(§2.2)
//  - PhotoReady 수신 → 사진 GET → 분류 → 정규화 → 결과 전송. 실패·지연(deadline) 시 other 폴백(§6)
//  - 하트비트 seq 정지 감지 → stalled

import Foundation

struct TimeoutError: Error {}

/// op을 deadline 내에 완료하지 못하면 TimeoutError. (§6 iPad측 deadline < Pi 15초)
func withTimeout<T: Sendable>(
    _ seconds: TimeInterval,
    _ op: @escaping @Sendable () async throws -> T
) async throws -> T {
    try await withThrowingTaskGroup(of: T.self) { group in
        group.addTask { try await op() }
        group.addTask {
            try await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
            throw TimeoutError()
        }
        defer { group.cancelAll() }
        return try await group.next()!
    }
}

@MainActor
public final class SessionCoordinator {
    public enum SessionState: Equatable, Sendable {
        case disconnected
        case incompatible(proto: Int)
        case attract                       // Pi idle·started, 투입 대기
        case processing(PiState)           // 감지/촬영/대기/sort 진행 시각화
        case reward(WasteCategory)         // sort 완료 → 결과 + 씨앗 추첨
        case error(ErrorCode)
        case maintenance
        case stalled                       // 하트비트 정지(Pi 응답 없음)
    }

    public private(set) var state: SessionState = .disconnected {
        didSet { if state != oldValue { onStateChange?(state) } }
    }
    public var onStateChange: ((SessionState) -> Void)?
    public var onPhotoData: ((Data) -> Void)?   // UI 사진 표시용

    private let link: PeripheralLink
    private let fetcher: PhotoFetcher
    private let classifier: ClassificationService
    private let normalizer: CategoryNormalizer
    private let clock: @Sendable () -> Date
    private let stallThreshold: TimeInterval
    private let resultDeadline: TimeInterval

    private var device: DeviceInfo?
    private var prevPiState: PiState?
    private var lastSeq: Int?
    private var lastSeqAt: Date?
    private var nextCommandId = 1
    private var activeCycle: Int?       // §2.2 상관: 현재 처리 중인 분류 사이클
    private var incompatible = false    // proto 불일치 sticky

    public init(
        link: PeripheralLink,
        fetcher: PhotoFetcher,
        classifier: ClassificationService,
        normalizer: CategoryNormalizer = CategoryNormalizer(),
        clock: @escaping @Sendable () -> Date = Date.init,
        stallThreshold: TimeInterval = 6.0,
        resultDeadline: TimeInterval = 12.0   // Pi 15초보다 짧게 — §6 보장
    ) {
        self.link = link
        self.fetcher = fetcher
        self.classifier = classifier
        self.normalizer = normalizer
        self.clock = clock
        self.stallThreshold = stallThreshold
        self.resultDeadline = resultDeadline
    }

    // MARK: 연결 이벤트 (어댑터가 호출)
    public func connected(_ device: DeviceInfo) {
        self.device = device
        guard device.proto == Proto.version else {
            incompatible = true
            state = .incompatible(proto: device.proto)
            return                       // §7 동작 차단 — start 안 보냄
        }
        incompatible = false
        sendCommand(.start)              // §2.1 어트랙트에서 감지 시작
        state = .attract
    }

    public func disconnected() {
        device = nil
        prevPiState = nil
        lastSeq = nil
        lastSeqAt = nil
        activeCycle = nil
        incompatible = false
        state = .disconnected
    }

    // MARK: Status 수신 — UI 구동 + §2.2 정합화 + §2.1 게이팅
    public func received(_ status: Status) {
        if incompatible { return }       // sticky 차단
        markSeq(status.seq)
        defer { prevPiState = status.state }

        switch status.state {
        case .error:
            state = .error(status.err ?? .internal)
        case .maintenance:
            state = .maintenance
        case .detecting, .capturing, .awaitingResult:
            state = .processing(status.state)
        case .sorting:
            // §2.1 게이팅: sort 진입 시 미리 stop → idle 복귀 시 다음 detection 레이스 방지.
            // 실제 분류 사이클(activeCycle)에 한정한다(운영자 수동 sort 제외).
            if prevPiState != .sorting, activeCycle != nil {
                sendCommand(.stop)
            }
            state = .processing(.sorting)
        case .idle:
            if prevPiState == .sorting, status.cycle == activeCycle {
                // sort 완료 → Pi의 실제 lastSort를 진실로 표시(§2.2). 우리 분류와 달라도 Pi를 따른다.
                state = .reward(status.lastSort ?? .other)
            } else if case .reward = state {
                break                    // 보상/씨앗 화면 유지(하트비트로 어트랙트 복귀 안 함)
            } else {
                state = .attract
            }
        }
    }

    // MARK: PhotoReady 수신 → 사진 GET → 분류 → 정규화 → 결과 전송(§6 폴백)
    public func received(_ photo: PhotoReady) async {
        guard let device, !incompatible else { return }
        activeCycle = photo.cycle
        let fetcher = self.fetcher
        let classifier = self.classifier
        let result: ClassificationResult
        do {
            let outcome = try await withTimeout(resultDeadline) { () -> (Data, RawClassification) in
                let data = try await fetcher.fetch(photo, from: device)
                let raw = try await classifier.classify(imageData: data)
                return (data, raw)
            }
            onPhotoData?(outcome.0)
            result = normalizer.normalize(outcome.1, cycle: photo.cycle)
        } catch {
            let reason = error is TimeoutError ? "timeout" : "error"
            result = normalizer.fallback(cycle: photo.cycle, reason: reason)
        }
        link.writeResult(result)         // cycle echo로 Pi가 상관
    }

    public func received(_ ack: CommandAck) {
        // 스캐폴드: 명령 ack 로깅/디버그 지점.
    }

    // MARK: 씨앗 인터랙션 종료 → 어트랙트 복귀 + 감지 재개(§2.1)
    public func seedInteractionFinished() {
        activeCycle = nil
        sendCommand(.start)
        state = .attract
    }

    // MARK: 하트비트 정지 감지 — UI 타이머가 주기 호출
    public func checkHeartbeat() {
        guard device != nil, !incompatible, let at = lastSeqAt else { return }
        if clock().timeIntervalSince(at) > stallThreshold {
            state = .stalled
        }
    }

    // MARK: 운영자(정비) 화면 패스스루
    public func sendOperatorCommand(_ type: CommandType, arg: String? = nil) {
        sendCommand(type, arg: arg)
    }

    // MARK: 내부
    private func markSeq(_ seq: Int) {
        if seq != lastSeq {
            lastSeq = seq
            lastSeqAt = clock()
        }
    }

    private func sendCommand(_ type: CommandType, arg: String? = nil) {
        link.writeCommand(Command(cmd: type, id: nextCommandId, arg: arg))
        nextCommandId += 1
    }
}
