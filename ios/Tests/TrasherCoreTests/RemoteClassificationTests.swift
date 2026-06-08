// RemoteClassificationService 골격 테스트 — URLProtocol 스텁.
import XCTest
@testable import TrasherCore

private final class RemoteStubProtocol: URLProtocol {
    nonisolated(unsafe) static var handler: ((URLRequest) -> (HTTPURLResponse, Data))?
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        guard let handler = Self.handler else {
            client?.urlProtocol(self, didFailWithError: URLError(.unknown)); return
        }
        let (response, data) = handler(request)
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

final class RemoteClassificationTests: XCTestCase {
    private func stubSession() -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [RemoteStubProtocol.self]
        return URLSession(configuration: config)
    }

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
        RemoteStubProtocol.handler = { req in
            XCTAssertEqual(req.httpMethod, "POST")
            let json = #"{"label":"aluminum_can","confidence":0.81}"#.data(using: .utf8)!
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

    func testNon200Throws() async {
        RemoteStubProtocol.handler = { req in
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
        RemoteStubProtocol.handler = { req in
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
