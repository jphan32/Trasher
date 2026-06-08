// iPad 사이클 조정자 — Pi 오케스트레이터의 iPad 대응물.
// docs/protocol.md §2.1(게이팅), §2.2(정합화), §6(폴백). 전부 mock으로 호스트 테스트 가능.
//
// 책임:
//  - 연결 시 proto 확인 → Command{start}로 감지 개시(§2.1)
//  - Status 수신 → UI 상태 구동. sort 완료 시 Pi의 lastSort를 진실로 결과 표시(§2.2)
//  - PhotoReady 수신 → 사진 GET → 분류 → 정규화 → 결과 전송. 실패 시 other 폴백(§6)
//  - 보상/씨앗 화면 동안 Command{stop}, 어트랙트 복귀 시 Command{start}(§2.1)
//  - 하트비트 seq 정지 감지 → stalled

import Foundation

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

    private var device: DeviceInfo?
    private var prevPiState: PiState?
    private var lastSeq: Int?
    private var lastSeqAt: Date?
    private var nextCommandId = 1

    public init(
        link: PeripheralLink,
        fetcher: PhotoFetcher,
        classifier: ClassificationService,
        normalizer: CategoryNormalizer = CategoryNormalizer(),
        clock: @escaping @Sendable () -> Date = Date.init,
        stallThreshold: TimeInterval = 6.0
    ) {
        self.link = link
        self.fetcher = fetcher
        self.classifier = classifier
        self.normalizer = normalizer
        self.clock = clock
        self.stallThreshold = stallThreshold
    }

    // MARK: 연결 이벤트 (어댑터가 호출)
    public func connected(_ device: DeviceInfo) {
        self.device = device
        guard device.proto == Proto.version else {
            state = .incompatible(proto: device.proto)
            return
        }
        sendCommand(.start)        // §2.1 어트랙트에서 감지 시작
        state = .attract
    }

    public func disconnected() {
        device = nil
        prevPiState = nil
        lastSeq = nil
        lastSeqAt = nil
        state = .disconnected
    }

    // MARK: Status 수신 — UI 구동 + §2.2 정합화 + §2.1 게이팅
    public func received(_ status: Status) {
        markSeq(status.seq)
        defer { prevPiState = status.state }

        switch status.state {
        case .error:
            state = .error(status.err ?? .internal)
        case .maintenance:
            state = .maintenance
        case .detecting, .capturing, .awaitingResult, .sorting:
            state = .processing(status.state)
        case .idle:
            if prevPiState == .sorting {
                // sort 완료 → Pi의 실제 lastSort를 진실로 표시(§2.2 정합화).
                // 우리가 보낸 분류와 달라도(타임아웃 자체처리 등) Pi 결과를 따른다.
                state = .reward(status.lastSort ?? .other)
                sendCommand(.stop)         // §2.1 보상/씨앗 동안 감지 중단
            } else if case .reward = state {
                // 보상/씨앗 화면 유지 — idle 하트비트로 어트랙트로 되돌리지 않음
                break
            } else {
                state = .attract
            }
        }
    }

    // MARK: PhotoReady 수신 → 사진 GET → 분류 → 정규화 → 결과 전송(§6 폴백)
    public func received(_ photo: PhotoReady) async {
        guard let device else { return }
        let result: ClassificationResult
        do {
            let data = try await fetcher.fetch(photo, from: device)
            onPhotoData?(data)
            let raw = try await classifier.classify(imageData: data)
            result = normalizer.normalize(raw, cycle: photo.cycle)
        } catch {
            result = normalizer.fallback(cycle: photo.cycle, reason: "error")
        }
        link.writeResult(result)       // cycle echo로 Pi가 상관
    }

    public func received(_ ack: CommandAck) {
        // 스캐폴드: 명령 ack 로깅/디버그 지점.
    }

    // MARK: 씨앗 인터랙션 종료 → 어트랙트 복귀 + 감지 재개(§2.1)
    public func seedInteractionFinished() {
        sendCommand(.start)
        state = .attract
    }

    // MARK: 하트비트 정지 감지 — UI 타이머가 주기 호출
    public func checkHeartbeat() {
        guard device != nil, let at = lastSeqAt else { return }
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
