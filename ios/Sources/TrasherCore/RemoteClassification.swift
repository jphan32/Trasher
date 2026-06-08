// 실제 분류 API용 ClassificationService 골격(제네릭 HTTP multipart 업로드).
// docs/protocol.md §4.5. API가 미정이라 엔드포인트·요청형식·응답 라벨/confidence 추출을 설정값으로 둔다.
// 실 API 확정 시 RemoteClassificationConfig만 채우면 된다(앱 나머지는 ClassificationService만 의존).

import Foundation

public enum RemoteClassificationError: Error, Equatable {
    case httpStatus(Int)
    case malformedResponse
}

/// 실 API 연동 설정. 응답 JSON에서 라벨/confidence를 꺼내는 키를 설정화.
public struct RemoteClassificationConfig: Sendable {
    public var endpoint: URL
    public var fileField: String        // multipart 파일 파트 이름
    public var labelKey: String         // 응답 JSON의 라벨 키
    public var confidenceKey: String    // 응답 JSON의 confidence 키

    public init(endpoint: URL, fileField: String = "image",
                labelKey: String = "label", confidenceKey: String = "confidence") {
        self.endpoint = endpoint
        self.fileField = fileField
        self.labelKey = labelKey
        self.confidenceKey = confidenceKey
    }
}

public struct RemoteClassificationService: ClassificationService {
    private let config: RemoteClassificationConfig
    private let session: URLSession
    private let boundaryProvider: @Sendable () -> String

    public init(
        config: RemoteClassificationConfig,
        session: URLSession = .shared,
        boundaryProvider: @escaping @Sendable () -> String = { "Boundary-\(UUID().uuidString)" }
    ) {
        self.config = config
        self.session = session
        self.boundaryProvider = boundaryProvider
    }

    public func classify(imageData: Data) async throws -> RawClassification {
        let boundary = boundaryProvider()
        var request = URLRequest(url: config.endpoint)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        request.httpBody = Self.multipartBody(imageData: imageData, field: config.fileField, boundary: boundary)

        let (data, response) = try await session.data(for: request)
        if let http = response as? HTTPURLResponse, http.statusCode != 200 {
            throw RemoteClassificationError.httpStatus(http.statusCode)
        }
        guard
            let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any],
            let label = obj[config.labelKey] as? String,
            let confidence = (obj[config.confidenceKey] as? NSNumber)?.doubleValue
        else {
            throw RemoteClassificationError.malformedResponse
        }
        return RawClassification(label: label, confidence: confidence)
    }

    static func multipartBody(imageData: Data, field: String, boundary: String) -> Data {
        var body = Data()
        func append(_ s: String) { body.append(s.data(using: .utf8)!) }
        append("--\(boundary)\r\n")
        append("Content-Disposition: form-data; name=\"\(field)\"; filename=\"trash.jpg\"\r\n")
        append("Content-Type: image/jpeg\r\n\r\n")
        body.append(imageData)
        append("\r\n--\(boundary)--\r\n")
        return body
    }
}
