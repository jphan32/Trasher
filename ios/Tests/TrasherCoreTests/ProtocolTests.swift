// 프로토콜 미러 라운드트립 + 와이어 호환(null 생략) 검증. docs/protocol.md §3.
import XCTest
@testable import TrasherCore

final class ProtocolTests: XCTestCase {
    func testUUIDsShareBase() {
        let base = String(Proto.serviceUUID.dropFirst(8))
        for uuid in [Proto.charDeviceInfo, Proto.charStatus, Proto.charPhotoReady,
                     Proto.charClassificationResult, Proto.charCommand, Proto.charCommandAck] {
            XCTAssertEqual(String(uuid.dropFirst(8)), base)
        }
        XCTAssertEqual(Proto.version, 1)
    }

    func testCategories() {
        XCTAssertEqual(Set(WasteCategory.allCases.map(\.rawValue)), ["pet", "can", "other"])
    }

    func testStatusRoundtrip() throws {
        let s = Status(state: .sorting, cycle: 42, seq: 7, err: .resultTimeout, lastSort: .other)
        let decoded = try Wire.decode(Status.self, from: Wire.encode(s))
        XCTAssertEqual(decoded, s)
    }

    func testStatusOmitsNilKeys() throws {
        let s = Status(state: .idle, cycle: 0, seq: 1)
        let json = String(data: try Wire.encode(s), encoding: .utf8)!
        XCTAssertFalse(json.contains("err"))       // nil → 키 생략
        XCTAssertFalse(json.contains("lastSort"))
    }

    func testStatusDecodesWithAbsentOptionals() throws {
        // Pi가 보낸 null-생략 페이로드를 키 부재 ≡ nil로 디코드.
        let json = #"{"state":"idle","cycle":0,"seq":1}"#.data(using: .utf8)!
        let s = try Wire.decode(Status.self, from: json)
        XCTAssertNil(s.err)
        XCTAssertNil(s.lastSort)
    }

    func testStateRawValues() {
        XCTAssertEqual(PiState.awaitingResult.rawValue, "awaiting_result")
        XCTAssertEqual(ErrorCode.resultTimeout.rawValue, "result_timeout")
        XCTAssertEqual(ErrorCode.internal.rawValue, "internal")
    }

    func testClassificationResultWireKeys() throws {
        let cr = ClassificationResult(cycle: 42, category: .pet, confidence: 0.93, raw: "PET_bottle")
        let json = String(data: try Wire.encode(cr), encoding: .utf8)!
        XCTAssertTrue(json.contains("\"category\":\"pet\""))
        let decoded = try Wire.decode(ClassificationResult.self, from: Wire.encode(cr))
        XCTAssertEqual(decoded, cr)
    }

    func testCommandRoundtrip() throws {
        let c = Command(cmd: .sort, id: 7, arg: "pet")
        XCTAssertEqual(try Wire.decode(Command.self, from: Wire.encode(c)), c)
    }

    func testDeviceInfoRoundtrip() throws {
        let di = DeviceInfo(fw: "0.1.0", ip: "192.168.0.5", port: 8080)
        let decoded = try Wire.decode(DeviceInfo.self, from: Wire.encode(di))
        XCTAssertEqual(decoded, di)
        XCTAssertEqual(decoded.proto, 1)
    }
}
