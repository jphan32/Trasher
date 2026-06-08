// CoreBluetooth Central 구현 — Pi(Peripheral)를 스캔·연결하고 특성 I/O를 코디네이터에 중계.
// docs/protocol.md §1(GATT), 연결 직후 브링업 순서(구독 확인 → DeviceInfo → start).
//
// ⚠️ 실 BLE 하드웨어/실기기 필요 → 호스트 단위테스트 불가(Pi의 bless와 동일 성격).
//    파싱/조정 로직은 TrasherCore(Protocol/SessionCoordinator)에서 테스트되고, 이 파일은 얇은 글루다.
//
// 동시성: central 큐를 main으로 두어 CoreBluetooth 콜백과 @MainActor 코디네이터를 같은 스레드에 둔다.

import Foundation
@preconcurrency import CoreBluetooth

public final class BLECentral: NSObject, PeripheralLink {
    /// 늦은 바인딩(순환 의존 회피): coordinator는 link를 strong-hold, BLECentral은 weak-hold.
    public weak var coordinator: SessionCoordinator?
    private var central: CBCentralManager!
    private var peripheral: CBPeripheral?
    private var chars: [String: CBCharacteristic] = [:]

    // 브링업 게이팅: notify 3개 구독 확인 + DeviceInfo read 후에만 connected() 호출.
    private static let notifyUUIDs: [CBUUID] = [Proto.charStatus, Proto.charPhotoReady, Proto.charCommandAck]
        .map { CBUUID(string: $0) }
    private var subscribed: Set<CBUUID> = []
    private var pendingDeviceInfo: DeviceInfo?
    private var announced = false

    public override init() {
        super.init()
        central = CBCentralManager(delegate: self, queue: .main)
    }

    public func start() {
        if central.state == .poweredOn { scan() }
    }

    private func scan() {
        guard central.state == .poweredOn else { return }  // 라디오 off면 no-op(상태 콜백에서 재시도)
        central.scanForPeripherals(withServices: [CBUUID(string: Proto.serviceUUID)])
    }

    private func resetConnectionState() {
        chars.removeAll()
        subscribed.removeAll()
        pendingDeviceInfo = nil
        announced = false
    }

    // 브링업 완료 판정: 구독 3개 + DeviceInfo 확보 시 1회 connected().
    private func announceReadyIfNeeded() {
        guard !announced, let di = pendingDeviceInfo,
              Set(Self.notifyUUIDs).isSubset(of: subscribed) else { return }
        announced = true
        onMain { $0.connected(di) }
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
        resetConnectionState()
        peripheral.delegate = self
        peripheral.discoverServices([CBUUID(string: Proto.serviceUUID)])
    }

    public func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral,
                               error: Error?) {
        self.peripheral = nil
        resetConnectionState()
        scan()  // 연결 실패 → 재스캔(영구 정지 방지)
    }

    public func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral,
                               error: Error?) {
        self.peripheral = nil  // dangling 참조 정리(didFailToConnect와 대칭)
        resetConnectionState()
        onMain { $0.disconnected() }
        scan()  // 자동 재연결(라디오 off면 scan이 no-op, 상태 콜백에서 재시도)
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
        let notifySet = Set(Self.notifyUUIDs)
        for ch in service.characteristics ?? [] {
            chars[ch.uuid.uuidString.lowercased()] = ch
            if notifySet.contains(ch.uuid) {
                peripheral.setNotifyValue(true, for: ch)
            }
            if ch.uuid == CBUUID(string: Proto.charDeviceInfo) {
                peripheral.readValue(for: ch)
            }
        }
    }

    // 구독(CCCD) enable 확인 → 브링업 게이팅
    public func peripheral(_ peripheral: CBPeripheral, didUpdateNotificationStateFor characteristic: CBCharacteristic,
                           error: Error?) {
        guard error == nil, characteristic.isNotifying else { return }
        subscribed.insert(characteristic.uuid)
        announceReadyIfNeeded()
    }

    public func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic,
                           error: Error?) {
        guard let data = characteristic.value else { return }
        switch characteristic.uuid {
        case CBUUID(string: Proto.charDeviceInfo):
            if let di = try? Wire.decode(DeviceInfo.self, from: data) {
                pendingDeviceInfo = di
                announceReadyIfNeeded()  // 구독 완료 후에만 connected()
            }
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
