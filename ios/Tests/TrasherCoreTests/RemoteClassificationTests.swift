// RemoteClassificationService 골격 테스트 — URLProtocol 스텁(StubURLProtocol 공유).
import XCTest
@testable import TrasherCore

final class RemoteClassificationTests: XCTestCase {
    private func stubSession() -> URLSession { makeStubSession() }

    private var config: RemoteClassificationConfig {
        RemoteClassificationConfig(endpoint: URL(string: "https://api.example.com/classify")!)
    }

    func testMultipartBodyShape() {
        let body = RemoteClassificationService.multipartBody(
            imageData: Data([0xFF, 0xD8]), field: "image", boundary: "B"
        )
        let text = String(data: body, encoding: .isoLatin1)!
        XCTAssertTrue(text.contains("--B\r\n"))
        XCTAssertTrue(text.contains("name=\"image\""))
        XCTAssertTrue(text.hasSuffix("--B--\r\n"))
    }

    func testClassifyParsesLabelAndConfidence() async throws {
        StubURLProtocol.handler = { req in
            XCTAssertEqual(req.httpMethod, "POST")
            let json = #"{"category":"aluminum_can","confidence":0.81}"#.data(using: .utf8)!
            return (HTTPURLResponse(url: req.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, json)
        }
        let svc = RemoteClassificationService(config: config, session: stubSession(),
                                              boundaryProvider: { "B" })
        let raw = try await svc.classify(imageData: Data([0xFF, 0xD8]))
        XCTAssertEqual(raw.label, "aluminum_can")
        XCTAssertEqual(raw.confidence, 0.81, accuracy: 1e-9)
        // 정규화까지: aluminum_can → can
        XCTAssertEqual(CategoryNormalizer().normalize(raw, cycle: 1).category, .can)
    }

    func testParsesDescriptionTip() async throws {
        StubURLProtocol.handler = { req in
            let json = #"{"category":"can","confidence":0.9,"description":"캔은 헹궈서 배출하세요."}"#
                .data(using: .utf8)!
            return (HTTPURLResponse(url: req.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, json)
        }
        let svc = RemoteClassificationService(config: config, session: stubSession())
        let raw = try await svc.classify(imageData: Data([0xFF, 0xD8]))
        XCTAssertEqual(raw.label, "can")
        XCTAssertEqual(raw.description, "캔은 헹궈서 배출하세요.")  // 재활용 팁 파싱
    }

    func testConfidenceAsStringIsAccepted() async throws {
        StubURLProtocol.handler = { req in
            let json = #"{"category":"pet","confidence":"0.93"}"#.data(using: .utf8)!
            return (HTTPURLResponse(url: req.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, json)
        }
        let svc = RemoteClassificationService(config: config, session: stubSession())
        let raw = try await svc.classify(imageData: Data([0xFF, 0xD8]))
        XCTAssertEqual(raw.label, "pet")
        XCTAssertEqual(raw.confidence, 0.93, accuracy: 1e-9)  // 문자열 confidence 허용
    }

    func testNon200Throws() async {
        StubURLProtocol.handler = { req in
            (HTTPURLResponse(url: req.url!, statusCode: 503, httpVersion: nil, headerFields: nil)!, Data())
        }
        let svc = RemoteClassificationService(config: config, session: stubSession())
        do {
            _ = try await svc.classify(imageData: Data())
            XCTFail("기대: httpStatus")
        } catch {
            XCTAssertEqual(error as? RemoteClassificationError, .httpStatus(503))
        }
    }

    func testMalformedResponseThrows() async {
        StubURLProtocol.handler = { req in
            let json = #"{"unexpected":true}"#.data(using: .utf8)!
            return (HTTPURLResponse(url: req.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, json)
        }
        let svc = RemoteClassificationService(config: config, session: stubSession())
        do {
            _ = try await svc.classify(imageData: Data())
            XCTFail("기대: malformedResponse")
        } catch {
            XCTAssertEqual(error as? RemoteClassificationError, .malformedResponse)
        }
    }
}
