// PiClassificationService 테스트 — Pi /classify/{cycle} 호출(StubURLProtocol).
import XCTest
@testable import TrasherCore

final class PiClassificationTests: XCTestCase {
    private let device = DeviceInfo(fw: "0.1.0", ip: "127.0.0.1", port: 8080)

    func testClassifyCallsCycleEndpointAndParses() async throws {
        StubURLProtocol.handler = { req in
            XCTAssertEqual(req.url?.absoluteString, "http://127.0.0.1:8080/classify/42")
            XCTAssertEqual(req.httpMethod, "POST")
            let json = #"{"category":"can","description":"캔은 헹궈서 배출.","confidence":0.9}"#
                .data(using: .utf8)!
            return (HTTPURLResponse(url: req.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, json)
        }
        let svc = PiClassificationService(session: makeStubSession())
        let raw = try await svc.classify(cycle: 42, on: device)
        XCTAssertEqual(raw.label, "can")
        XCTAssertEqual(raw.confidence, 0.9, accuracy: 1e-9)
        XCTAssertEqual(raw.description, "캔은 헹궈서 배출.")  // 재활용 팁
    }

    func testConfidenceAsStringAccepted() async throws {
        StubURLProtocol.handler = { req in
            let json = #"{"category":"pet","confidence":"0.93"}"#.data(using: .utf8)!
            return (HTTPURLResponse(url: req.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, json)
        }
        let raw = try await PiClassificationService(session: makeStubSession()).classify(cycle: 1, on: device)
        XCTAssertEqual(raw.label, "pet")
        XCTAssertEqual(raw.confidence, 0.93, accuracy: 1e-9)
    }

    func testNon200Throws() async {
        StubURLProtocol.handler = { req in
            (HTTPURLResponse(url: req.url!, statusCode: 502, httpVersion: nil, headerFields: nil)!, Data())
        }
        do {
            _ = try await PiClassificationService(session: makeStubSession()).classify(cycle: 1, on: device)
            XCTFail("기대: httpStatus")
        } catch {
            XCTAssertEqual(error as? PiClassificationError, .httpStatus(502))
        }
    }

    func testMalformedResponseThrows() async {
        StubURLProtocol.handler = { req in
            let json = #"{"unexpected":true}"#.data(using: .utf8)!
            return (HTTPURLResponse(url: req.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, json)
        }
        do {
            _ = try await PiClassificationService(session: makeStubSession()).classify(cycle: 1, on: device)
            XCTFail("기대: malformedResponse")
        } catch {
            XCTAssertEqual(error as? PiClassificationError, .malformedResponse)
        }
    }
}
