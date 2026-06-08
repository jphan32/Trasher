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
        guard
            let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any],
            let category = obj["category"] as? String,
            let confidence = Self.asDouble(obj["confidence"])
        else {
            throw PiClassificationError.malformedResponse
        }
        let description = obj["description"] as? String   // 재활용 팁(없을 수 있음)
        return RawClassification(label: category, confidence: confidence, description: description)
    }

    /// confidence를 숫자 또는 숫자형 문자열("0.93") 양쪽에서 허용.
    static func asDouble(_ value: Any?) -> Double? {
        if let n = value as? NSNumber { return n.doubleValue }
        if let s = value as? String { return Double(s) }
        return nil
    }
}
