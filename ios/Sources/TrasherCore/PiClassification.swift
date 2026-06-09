// Pi /classify/{cycle} 호출 분류 서비스. docs/protocol.md §4.4.
//
// 트래픽 최적화: 이미지를 재업로드하지 않고 cycle ID만 보낸다. Pi가 이미 보유한 로컬 사진을
// 읽어 Gemini(structured output)로 분류하고 {category, description(재활용 팁), confidence}를 반환.
// 호출 주체·결과 핸들러는 iPad(이 서비스) — UI 표시 + BLE로 3분류 전달은 iPad가 주도한다.

import Foundation

public enum PiClassificationError: Error, Equatable {
    case badURL
    case httpStatus(Int)
    case malformedResponse
}

public struct PiClassificationService: ClassificationService {
    private let session: URLSession
    public init(session: URLSession = .shared) {
        self.session = session
    }

    public func classify(cycle: Int, on device: DeviceInfo) async throws -> RawClassification {
        guard let url = URL(string: "http://\(device.ip):\(device.port)/classify/\(cycle)") else {
            throw PiClassificationError.badURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = "POST"

        let (data, response) = try await session.data(for: request)
        if let http = response as? HTTPURLResponse, http.statusCode != 200 {
            throw PiClassificationError.httpStatus(http.statusCode)
        }
        // 200인데 본문이 JSON이 아니거나 키가 없으면 일관되게 malformedResponse.
        guard
            let parsed = try? JSONSerialization.jsonObject(with: data),
            let obj = parsed as? [String: Any],
            let category = obj["category"] as? String,
            let confidence = Self.asDouble(obj["confidence"])
        else {
            throw PiClassificationError.malformedResponse
        }
        let description = obj["description"] as? String   // 재활용 팁(없을 수 있음)
        let ecoPoints = Self.asInt(obj["eco_points"])     // 탄소절감 에코포인트(없을 수 있음)
        let recyclable = Self.asBool(obj["recyclable"])   // 재활용 가능 여부(없을 수 있음)
        return RawClassification(
            label: category, confidence: confidence, description: description,
            ecoPoints: ecoPoints, recyclable: recyclable
        )
    }

    /// confidence를 숫자 또는 숫자형 문자열("0.93") 양쪽에서 허용.
    static func asDouble(_ value: Any?) -> Double? {
        if let n = value as? NSNumber { return n.doubleValue }
        if let s = value as? String { return Double(s) }
        return nil
    }

    /// eco_points를 숫자 또는 숫자형 문자열에서 허용(없으면 nil).
    static func asInt(_ value: Any?) -> Int? {
        if let n = value as? NSNumber { return n.intValue }
        if let s = value as? String { return Int(s) }
        return nil
    }

    /// recyclable을 Bool 또는 0/1 숫자에서 허용(없으면 nil).
    static func asBool(_ value: Any?) -> Bool? {
        if let b = value as? Bool { return b }
        if let n = value as? NSNumber { return n.boolValue }
        return nil
    }
}
