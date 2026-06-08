// BLE 전송 추상화 (코디네이터 관점). docs/protocol.md §3.
//
// SessionCoordinator는 이 프로토콜로 Pi에 write만 한다(아웃바운드).
// 인바운드(Status/PhotoReady/CommandAck/연결상태)는 어댑터가 코디네이터의 received(_:)를 호출해 push한다.
// 실제 구현은 CoreBluetooth(BLECentral), 테스트는 MockPeripheralLink.

import Foundation

/// 코디네이터 → Pi 아웃바운드 write.
public protocol PeripheralLink: AnyObject {
    func writeResult(_ result: ClassificationResult)
    func writeCommand(_ command: Command)
}

/// 테스트용 Mock. write 이력을 기록한다.
public final class MockPeripheralLink: PeripheralLink {
    public private(set) var results: [ClassificationResult] = []
    public private(set) var commands: [Command] = []
    public init() {}

    public func writeResult(_ result: ClassificationResult) {
        results.append(result)
    }
    public func writeCommand(_ command: Command) {
        commands.append(command)
    }

    public var lastCommand: Command? { commands.last }
    public var lastResult: ClassificationResult? { results.last }
}
