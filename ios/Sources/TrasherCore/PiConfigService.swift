// Pi 런타임 설정 GET/PUT 서비스. docs/protocol.md §8.
//
// PhotoFetcher/PiClassificationService와 동일 패턴: URLSession 주입(테스트 시 StubURLProtocol),
// DeviceInfo의 ip:port로 base URL 도출, async/throws. 운영자 화면 전용(참여자 흐름 무관).

import Foundation

public enum PiConfigError: Error, Equatable {
    case notConnected          // 현재 연결된 Pi(DeviceInfo) 없음 — 운영자에게 안내
    case badURL
    case httpStatus(Int)       // 비-200(400 unknown field / 503 등)
    case malformedResponse     // 200이지만 본문이 기대 스키마가 아님
}

/// `PUT /config` 결과. `applied`=Pi가 clamp 후 실제 적용한 값, `persisted`=영속 저장 여부(§8.2).
public struct PiConfigApplyResult: Equatable, Sendable {
    public let applied: [String: Double]
    public let persisted: Bool   // false ⇒ 메모리엔 적용됐으나 디스크 저장 실패(재시작 시 소실)
    public init(applied: [String: Double], persisted: Bool) {
        self.applied = applied
        self.persisted = persisted
    }
}

public struct PiConfigService: Sendable {
    private let session: URLSession
    public init(session: URLSession = .shared) {
        self.session = session
    }

    /// `http://{ip}:{port}/config`.
    public func configURL(device: DeviceInfo) -> URL? {
        URL(string: "http://\(device.ip):\(device.port)/config")
    }

    /// `GET /config` — 현재 튜닝값+스키마(§8.1).
    public func getConfig(on device: DeviceInfo) async throws -> PiConfigSnapshot {
        guard let url = configURL(device: device) else { throw PiConfigError.badURL }
        let (data, response) = try await session.data(from: url)
        if let http = response as? HTTPURLResponse, http.statusCode != 200 {
            throw PiConfigError.httpStatus(http.statusCode)
        }
        do {
            return try JSONDecoder().decode(PiConfigSnapshot.self, from: data)
        } catch {
            throw PiConfigError.malformedResponse
        }
    }

    /// `PUT /config` — 변경분만 전송(§8.2). 반환: 적용값 + 영속 저장 여부.
    @discardableResult
    public func putConfig(
        _ changes: [String: Double], on device: DeviceInfo
    ) async throws -> PiConfigApplyResult {
        guard let url = configURL(device: device) else { throw PiConfigError.badURL }
        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: changes)

        let (data, response) = try await session.data(for: request)
        if let http = response as? HTTPURLResponse, http.statusCode != 200 {
            throw PiConfigError.httpStatus(http.statusCode)
        }
        // 응답 {ok, applied:{key:clamped}, persisted} — applied(실제 적용값)로 UI가 슬라이더 보정.
        guard
            let parsed = try? JSONSerialization.jsonObject(with: data),
            let obj = parsed as? [String: Any],
            let applied = obj["applied"] as? [String: Any]
        else {
            throw PiConfigError.malformedResponse
        }
        var result: [String: Double] = [:]
        for (key, raw) in applied {
            if let number = raw as? NSNumber { result[key] = number.doubleValue }
        }
        // persisted 키 부재 시 true로 간주(전방호환 — §8.2).
        let persisted = (obj["persisted"] as? NSNumber)?.boolValue ?? true
        return PiConfigApplyResult(applied: result, persisted: persisted)
    }
}
