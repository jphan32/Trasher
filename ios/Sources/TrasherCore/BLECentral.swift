// CoreBluetooth Central 구현 — Pi(Peripheral)를 스캔·연결하고 특성 I/O를 코디네이터에 중계.
// docs/protocol.md §1(GATT), 브링업 순서.
//
// ⚠️ 실 BLE 하드웨어/실기기 필요 → 호스트 단위테스트 불가(Pi의 bless와 동일 성격).
//    파싱/조정 로직은 TrasherCore(Protocol/SessionCoordinator)에서 테스트되고, 이 파일은 얇은 글루다.
//
// 동시성: central 큐를 main으로 두어 CoreBluetooth 콜백과 @MainActor 코디네이터를 같은 스레드에 둔다.
// 코디네이터 호출은 Task { @MainActor } 로 홉한다(async received(photo) 포함).

import Foundation
@preconcurrency import CoreBluetooth

public final class BLECentral: NSObject, PeripheralLink {
    /// 늦은 바인딩(순환 의존 회피): coordinator는 link를 strong-hold, BLECentral은 weak-hold.
    public weak var coordinator: SessionCoordinator?
    private var central: CBCentralManager!
    private var peripheral: CBPeripheral?
    private var chars: [String: CBCharacteristic] = [:]

    private static let notifyChars = [Proto.charStatus, Proto.charPhotoReady, Proto.charCommandAck]

    public override init() {
        super.init()
        central = CBCentralManager(delegate: self, queue: .main)
    }

    /// 광고 스캔 시작(poweredOn이면 즉시, 아니면 상태 콜백에서).
    public func start() {
        if central.state == .poweredOn { scan() }
    }

    private func scan() {
        central.scanForPeripherals(withServices: [CBUUID(string: Proto.serviceUUID)])
    }

    // MARK: PeripheralLink (coordinator가 MainActor에서 호출)
    public func writeResult(_ result: ClassificationResult) {
        write(result, to: Proto.charClassificationResult)
    }
    public func writeCommand(_ command: Command) {
        write(command, to: Proto.charCommand)
    }
    private func write<T: Encodable>(_ value: T, to uuid: String) {
        guard let peripheral, let ch = chars[uuid.lowercased()], let data = try? Wire.encode(value) else {
            return
        }
        peripheral.writeValue(data, for: ch, type: .withResponse)
    }

    // MARK: 코디네이터로 홉
    private func onMain(_ body: @escaping @MainActor (SessionCoordinator) -> Void) {
        guard let c = coordinator else { return }
        Task { @MainActor in body(c) }
    }
}

extension BLECentral: CBCentralManagerDelegate {
    public func centralManagerDidUpdateState(_ central: CBCentralManager) {
        if central.state == .poweredOn { scan() }
    }

    public func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral,
                               advertisementData: [String: Any], rssi RSSI: NSNumber) {
        self.peripheral = peripheral
        central.stopScan()
        central.connect(peripheral)
    }

    public func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        peripheral.delegate = self
        peripheral.discoverServices([CBUUID(string: Proto.serviceUUID)])
    }

    public func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral,
                               error: Error?) {
        chars.removeAll()
        onMain { $0.disconnected() }
        scan()  // 자동 재연결
    }
}

extension BLECentral: CBPeripheralDelegate {
    public func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        let svc = CBUUID(string: Proto.serviceUUID)
        for service in peripheral.services ?? [] where service.uuid == svc {
            peripheral.discoverCharacteristics(nil, for: service)
        }
    }

    public func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService,
                           error: Error?) {
        let notifySet = Set(Self.notifyChars.map { CBUUID(string: $0) })
        for ch in service.characteristics ?? [] {
            chars[ch.uuid.uuidString.lowercased()] = ch
            if notifySet.contains(ch.uuid) {
                peripheral.setNotifyValue(true, for: ch)
            }
            if ch.uuid == CBUUID(string: Proto.charDeviceInfo) {
                peripheral.readValue(for: ch)  // 연결 직후 DeviceInfo read
            }
        }
    }

    public func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic,
                           error: Error?) {
        guard let data = characteristic.value else { return }
        switch characteristic.uuid {
        case CBUUID(string: Proto.charDeviceInfo):
            if let di = try? Wire.decode(DeviceInfo.self, from: data) { onMain { $0.connected(di) } }
        case CBUUID(string: Proto.charStatus):
            if let s = try? Wire.decode(Status.self, from: data) { onMain { $0.received(s) } }
        case CBUUID(string: Proto.charPhotoReady):
            if let pr = try? Wire.decode(PhotoReady.self, from: data), let c = coordinator {
                Task { @MainActor in await c.received(pr) }
            }
        case CBUUID(string: Proto.charCommandAck):
            if let ack = try? Wire.decode(CommandAck.self, from: data) { onMain { $0.received(ack) } }
        default:
            break
        }
    }
}
