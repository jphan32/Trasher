// 교차언어 계약 적합성 — 골든 픽스처(fixtures/proto-v1/messages.json)를 Swift 모델로 라운드트립.
// Pi 측 pi/tests/test_contract_fixtures.py가 같은 파일을 검증한다. 드리프트 시 한쪽이 깨진다.
import XCTest
@testable import TrasherCore

final class ContractFixturesTests: XCTestCase {
    // ios/Tests/TrasherCoreTests/<this> → 위로 4단계 = repo 루트.
    private var fixtureURL: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()  // TrasherCoreTests
            .deletingLastPathComponent()  // Tests
            .deletingLastPathComponent()  // ios
            .deletingLastPathComponent()  // repo root
            .appendingPathComponent("fixtures/proto-v1/messages.json")
    }

    private func reencode(type: String, wire: [String: Any]) throws -> Data {
        let wireData = try JSONSerialization.data(withJSONObject: wire)
        switch type {
        case "DeviceInfo": return try Wire.encode(try Wire.decode(DeviceInfo.self, from: wireData))
        case "Status": return try Wire.encode(try Wire.decode(Status.self, from: wireData))
        case "PhotoReady": return try Wire.encode(try Wire.decode(PhotoReady.self, from: wireData))
        case "ClassificationResult":
            return try Wire.encode(try Wire.decode(ClassificationResult.self, from: wireData))
        case "Command": return try Wire.encode(try Wire.decode(Command.self, from: wireData))
        case "CommandAck": return try Wire.encode(try Wire.decode(CommandAck.self, from: wireData))
        default: XCTFail("알 수 없는 타입 \(type)"); return Data()
        }
    }

    func testFixtureRoundtripMatchesWire() throws {
        let data = try Data(contentsOf: fixtureURL)
        let root = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        XCTAssertEqual(root["proto"] as? Int, Proto.version)
        let cases = root["cases"] as! [[String: Any]]
        XCTAssertFalse(cases.isEmpty)

        for c in cases {
            let type = c["type"] as! String
            let wire = c["wire"] as! [String: Any]
            // 와이어 → 모델 → 와이어. null 생략 규약상 재인코드는 원본과 정확히 일치해야 한다.
            let reData = try reencode(type: type, wire: wire)
            let lhs = try JSONSerialization.jsonObject(with: reData) as! NSDictionary
            let rhs = wire as NSDictionary
            XCTAssertEqual(lhs, rhs, "\(type) 라운드트립 불일치")
        }
    }
}
