// /classify 응답 교차언어 계약 — 골든 픽스처(fixtures/classify-response.json) iOS 측 파싱 검증.
// Pi test_classify_contract.py가 같은 파일을 검증한다. 드리프트 시 한쪽이 깨진다.
import XCTest
@testable import TrasherCore

final class PiClassificationContractTests: XCTestCase {
    private let device = DeviceInfo(fw: "0.1.0", ip: "127.0.0.1", port: 8080)

    // ios/Tests/TrasherCoreTests/<this> → 위로 4단계 = repo 루트.
    private var fixtureURL: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()  // TrasherCoreTests
            .deletingLastPathComponent()  // Tests
            .deletingLastPathComponent()  // ios
            .deletingLastPathComponent()  // repo root
            .appendingPathComponent("fixtures/classify-response.json")
    }

    func testParsesAllGoldenResponses() async throws {
        let data = try Data(contentsOf: fixtureURL)
        let root = try JSONSerialization.jsonObject(with: data) as! [String: Any]
        XCTAssertEqual(root["proto"] as? Int, Proto.version)
        let cases = root["cases"] as! [[String: Any]]
        XCTAssertFalse(cases.isEmpty)

        for c in cases {
            let body = try JSONSerialization.data(withJSONObject: c)
            StubURLProtocol.handler = { req in
                (HTTPURLResponse(url: req.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, body)
            }
            let raw = try await PiClassificationService(session: makeStubSession())
                .classify(cycle: 1, on: device)
            XCTAssertEqual(raw.label, c["category"] as? String)
            XCTAssertEqual(raw.description, c["description"] as? String)
            XCTAssertEqual(raw.confidence, (c["confidence"] as! NSNumber).doubleValue, accuracy: 1e-9)
            // eco 필드도 골든과 일치하게 파싱(탄소절감 에코포인트·재활용 여부)
            XCTAssertEqual(raw.ecoPoints, (c["eco_points"] as! NSNumber).intValue)
            XCTAssertEqual(raw.recyclable, c["recyclable"] as? Bool)
            // 비재활용 케이스는 보상이 0개, 재활용 양수는 1개 이상
            let eco = EcoReward(raw: raw)
            if raw.recyclable == false { XCTAssertEqual(eco.lollipops, 0) }
            else if (raw.ecoPoints ?? 0) > 0 { XCTAssertGreaterThanOrEqual(eco.lollipops, 1) }
            // 정규화 시 3분류로 매핑됨(골든은 이미 pet/can/other)
            XCTAssertTrue(WasteCategory.allCases.map(\.rawValue).contains(raw.label))
        }
    }
}
