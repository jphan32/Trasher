// 분류 누적 집계(전시 홍보용). 완료 사이클마다 카테고리별 카운트.
// 순수/Codable — 호스트 테스트 + UserDefaults 영속.

import Foundation

public struct SortStats: Codable, Equatable, Sendable {
    public private(set) var counts: [WasteCategory: Int]

    public init(counts: [WasteCategory: Int] = [:]) {
        self.counts = counts
    }

    public var total: Int { counts.values.reduce(0, +) }

    public func count(_ category: WasteCategory) -> Int { counts[category] ?? 0 }

    public mutating func record(_ category: WasteCategory) {
        counts[category, default: 0] += 1
    }

    public func recording(_ category: WasteCategory) -> SortStats {
        var copy = self
        copy.record(category)
        return copy
    }

    // WasteCategory를 키로 쓰는 dictionary는 기본 Codable이 안 되므로 rawValue로 직렬화.
    private enum CodingKeys: String, CodingKey { case counts }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let raw = try c.decode([String: Int].self, forKey: .counts)
        var parsed: [WasteCategory: Int] = [:]
        for (k, v) in raw {
            if let cat = WasteCategory(rawValue: k) { parsed[cat] = v }
        }
        counts = parsed
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        let raw = Dictionary(uniqueKeysWithValues: counts.map { ($0.key.rawValue, $0.value) })
        try c.encode(raw, forKey: .counts)
    }
}
