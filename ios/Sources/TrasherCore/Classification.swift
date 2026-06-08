// 분류 추상화 + 라벨→3분류 정규화. docs/protocol.md §4.4, §4.5.
//
// 외부 분류 API가 미정이므로 ClassificationService 프로토콜 뒤에서 개발한다.
// 앱 나머지 코드는 mock/real을 구분하지 않는다. 실제 API 확정 시 RemoteClassificationService만 교체.

import Foundation

/// 외부 API의 원시 출력(라벨 + confidence). 정규화 전.
public struct RawClassification: Equatable, Sendable {
    public let label: String
    public let confidence: Double
    public init(label: String, confidence: Double) {
        self.label = label
        self.confidence = confidence
    }
}

/// 분류 서비스 추상화. 이미지 URL → 원시 분류.
public protocol ClassificationService: Sendable {
    func classify(imageURL: URL) async throws -> RawClassification
}

/// 개발/데모용 Mock. 고정 결과를 반환한다.
public struct MockClassificationService: ClassificationService {
    public let fixed: RawClassification
    public init(label: String = "pet", confidence: Double = 0.95) {
        self.fixed = RawClassification(label: label, confidence: confidence)
    }
    public func classify(imageURL: URL) async throws -> RawClassification {
        fixed
    }
}

/// 라벨→3분류 정규화 + confidence 임계값. §4.4. Pi에는 항상 3분류만 전달된다.
public struct CategoryNormalizer: Sendable {
    public let threshold: Double

    /// 소문자/트림된 라벨 → 카테고리. 미매핑은 other.
    private static let labelMap: [String: WasteCategory] = [
        "pet": .pet, "plastic_bottle": .pet, "pet_bottle": .pet,
        "페트": .pet, "플라스틱병": .pet,
        "can": .can, "aluminum_can": .can, "steel_can": .can,
        "캔": .can, "알루미늄캔": .can,
    ]

    public init(threshold: Double = 0.5) {
        self.threshold = threshold
    }

    /// 원시 분류를 3분류 결과로 정규화. 불확실(임계값 미만)이면 안전 기본값 other.
    public func normalize(_ raw: RawClassification, cycle: Int) -> ClassificationResult {
        let category = mapCategory(raw)
        return ClassificationResult(
            cycle: cycle, category: category, confidence: raw.confidence, raw: raw.label
        )
    }

    private func mapCategory(_ raw: RawClassification) -> WasteCategory {
        if raw.confidence < threshold { return .other }  // 불확실 → 안전 기본값
        let key = raw.label.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return Self.labelMap[key] ?? .other
    }

    /// 폴백 결과(HTTP/API 실패·타임아웃). §6 — Pi는 어떤 경우에도 결과를 받는다.
    public func fallback(cycle: Int, reason: String = "error") -> ClassificationResult {
        ClassificationResult(cycle: cycle, category: .other, confidence: 0, raw: reason)
    }
}
