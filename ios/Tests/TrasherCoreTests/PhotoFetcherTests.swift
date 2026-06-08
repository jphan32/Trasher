// 사진 다운로드 테스트 — URL 구성 + URLProtocol 스텁(StubURLProtocol 공유).
import XCTest
@testable import TrasherCore

final class PhotoFetcherTests: XCTestCase {
    private func stubSession() -> URLSession { makeStubSession() }

    func testPhotoURLConstruction() {
        let di = DeviceInfo(fw: "0.1.0", ip: "192.168.0.5", port: 8080)
        let pr = PhotoReady(cycle: 42, path: "/photos/42.jpg")
        XCTAssertEqual(photoURL(device: di, photo: pr)?.absoluteString,
                       "http://192.168.0.5:8080/photos/42.jpg")
    }

    func testFetchReturnsDataOn200() async throws {
        let di = DeviceInfo(fw: "0.1.0", ip: "127.0.0.1", port: 8080)
        let pr = PhotoReady(cycle: 7, path: "/photos/7.jpg")
        let payload = Data([0xFF, 0xD8, 0x01, 0x02, 0xFF, 0xD9])
        StubURLProtocol.handler = { req in
            XCTAssertEqual(req.url?.absoluteString, "http://127.0.0.1:8080/photos/7.jpg")
            let resp = HTTPURLResponse(url: req.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
            return (resp, payload)
        }
        let fetcher = URLSessionPhotoFetcher(session: stubSession())
        let data = try await fetcher.fetch(pr, from: di)
        XCTAssertEqual(data, payload)
    }

    func testFetchThrowsOnNon200() async {
        let di = DeviceInfo(fw: "0.1.0", ip: "127.0.0.1", port: 8080)
        let pr = PhotoReady(cycle: 9, path: "/photos/9.jpg")
        StubURLProtocol.handler = { req in
            (HTTPURLResponse(url: req.url!, statusCode: 404, httpVersion: nil, headerFields: nil)!, Data())
        }
        let fetcher = URLSessionPhotoFetcher(session: stubSession())
        do {
            _ = try await fetcher.fetch(pr, from: di)
            XCTFail("기대: 404 에러")
        } catch {
            XCTAssertEqual(error as? PhotoFetchError, .httpStatus(404))
        }
    }
}
