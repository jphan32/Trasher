// PiConfigService 테스트 — GET/PUT /config(StubURLProtocol). docs/protocol.md §8.
import XCTest
@testable import TrasherCore

final class PiConfigServiceTests: XCTestCase {
    private let device = DeviceInfo(fw: "0.1.0", ip: "127.0.0.1", port: 8080)

    override func tearDown() {
        StubURLProtocol.handler = nil
        super.tearDown()
    }

    // MARK: GET /config
    func testGetConfigParsesSchema() async throws {
        let json = """
        {"fw":"0.1.0","fields":[
          {"key":"belt_run_seconds","section":"belt","label":"벨트 구동 시간","unit":"s","type":"float","value":3.0,"min":0.5,"max":15.0,"step":0.1},
          {"key":"vision_motion_threshold","section":"vision","label":"모션 감지 임계값","unit":"","type":"float","value":0.02,"min":0.001,"max":0.5,"step":0.001}
        ]}
        """.data(using: .utf8)!
        StubURLProtocol.handler = { req in
            XCTAssertEqual(req.url?.absoluteString, "http://127.0.0.1:8080/config")
            XCTAssertEqual(req.httpMethod, "GET")
            return (Self.ok(req), json)
        }
        let snapshot = try await PiConfigService(session: makeStubSession()).getConfig(on: device)
        XCTAssertEqual(snapshot.fw, "0.1.0")
        XCTAssertEqual(snapshot.fields.count, 2)
        let belt = snapshot.fields[0]
        XCTAssertEqual(belt.key, "belt_run_seconds")
        XCTAssertEqual(belt.section, "belt")
        XCTAssertEqual(belt.value, 3.0)
        XCTAssertEqual(belt.min, 0.5)
        XCTAssertEqual(belt.max, 15.0)
        XCTAssertEqual(belt.step, 0.1)
        XCTAssertEqual(belt.unit, "s")
    }

    func testGetConfigHTTPErrorThrows() async {
        StubURLProtocol.handler = { req in (Self.status(req, 503), Data()) }
        await XCTAssertThrowsErrorAsync(
            try await PiConfigService(session: makeStubSession()).getConfig(on: device)
        ) { error in
            XCTAssertEqual(error as? PiConfigError, .httpStatus(503))
        }
    }

    func testGetConfigMalformedThrows() async {
        StubURLProtocol.handler = { req in (Self.ok(req), Data("not json".utf8)) }
        await XCTAssertThrowsErrorAsync(
            try await PiConfigService(session: makeStubSession()).getConfig(on: device)
        ) { error in
            XCTAssertEqual(error as? PiConfigError, .malformedResponse)
        }
    }

    // MARK: PUT /config
    func testPutConfigSendsDeltaAndParsesApplied() async throws {
        StubURLProtocol.handler = { req in
            XCTAssertEqual(req.url?.absoluteString, "http://127.0.0.1:8080/config")
            XCTAssertEqual(req.httpMethod, "PUT")
            // 보낸 본문이 정확히 변경 delta인지 검증(httpBodyStream 경유).
            let body = stubRequestBody(req)
            let sent = (try? JSONSerialization.jsonObject(with: body)) as? [String: Any]
            XCTAssertEqual(sent?["belt_run_seconds"] as? Double, 2.5)
            XCTAssertEqual(sent?.count, 1)
            let resp = #"{"ok":true,"applied":{"belt_run_seconds":2.5},"persisted":true}"#.data(using: .utf8)!
            return (Self.ok(req), resp)
        }
        let result = try await PiConfigService(session: makeStubSession())
            .putConfig(["belt_run_seconds": 2.5], on: device)
        XCTAssertEqual(result.applied, ["belt_run_seconds": 2.5])
        XCTAssertTrue(result.persisted)
    }

    func testPutConfigParsesClampedApplied() async throws {
        // 범위 밖 요청 → 서버가 clamp한 실제 적용값을 응답에 echo. 서비스는 그대로 반환.
        StubURLProtocol.handler = { req in
            let resp = #"{"ok":true,"applied":{"belt_run_seconds":15.0},"persisted":true}"#.data(using: .utf8)!
            return (Self.ok(req), resp)
        }
        let result = try await PiConfigService(session: makeStubSession())
            .putConfig(["belt_run_seconds": 999], on: device)
        XCTAssertEqual(result.applied["belt_run_seconds"], 15.0)
    }

    func testPutConfigPersistedFalseSurfaced() async throws {
        // 디스크 저장 실패 → persisted:false. UI가 "재시작 시 초기화" 경고에 사용.
        StubURLProtocol.handler = { req in
            let resp = #"{"ok":true,"applied":{"belt_run_seconds":2.5},"persisted":false}"#.data(using: .utf8)!
            return (Self.ok(req), resp)
        }
        let result = try await PiConfigService(session: makeStubSession())
            .putConfig(["belt_run_seconds": 2.5], on: device)
        XCTAssertFalse(result.persisted)
    }

    func testPutConfigMissingPersistedDefaultsTrue() async throws {
        // persisted 키 부재(구 Pi) → true로 간주(전방호환).
        StubURLProtocol.handler = { req in
            let resp = #"{"ok":true,"applied":{"belt_run_seconds":2.5}}"#.data(using: .utf8)!
            return (Self.ok(req), resp)
        }
        let result = try await PiConfigService(session: makeStubSession())
            .putConfig(["belt_run_seconds": 2.5], on: device)
        XCTAssertTrue(result.persisted)
    }

    func testPutConfigUnknownFieldHTTPError() async {
        StubURLProtocol.handler = { req in (Self.status(req, 400), Data()) }
        await XCTAssertThrowsErrorAsync(
            try await PiConfigService(session: makeStubSession())
                .putConfig(["bogus": 1], on: device)
        ) { error in
            XCTAssertEqual(error as? PiConfigError, .httpStatus(400))
        }
    }

    func testPutConfigMalformedResponseThrows() async {
        StubURLProtocol.handler = { req in (Self.ok(req), Data(#"{"ok":true}"#.utf8)) }
        await XCTAssertThrowsErrorAsync(
            try await PiConfigService(session: makeStubSession())
                .putConfig(["belt_run_seconds": 2.5], on: device)
        ) { error in
            XCTAssertEqual(error as? PiConfigError, .malformedResponse)
        }
    }

    func testConfigURL() {
        let url = PiConfigService().configURL(device: device)
        XCTAssertEqual(url?.absoluteString, "http://127.0.0.1:8080/config")
    }

    // MARK: helpers
    private static func ok(_ req: URLRequest) -> HTTPURLResponse { status(req, 200) }
    private static func status(_ req: URLRequest, _ code: Int) -> HTTPURLResponse {
        HTTPURLResponse(url: req.url!, statusCode: code, httpVersion: nil, headerFields: nil)!
    }
}

/// async throws 단언 헬퍼(XCTAssertThrowsError의 async 버전).
func XCTAssertThrowsErrorAsync<T>(
    _ expression: @autoclosure () async throws -> T,
    _ errorHandler: (Error) -> Void,
    file: StaticString = #filePath, line: UInt = #line
) async {
    do {
        _ = try await expression()
        XCTFail("기대한 오류가 발생하지 않음", file: file, line: line)
    } catch {
        errorHandler(error)
    }
}
