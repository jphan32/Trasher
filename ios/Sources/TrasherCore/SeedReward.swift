// 씨앗 5종 랜덤 추첨. 분류 완료 후 참여자에게 1종 제공(재고 무관). CLAUDE.md 동작 시퀀스.
// RNG 주입으로 테스트에서 결정적으로 검증.

public struct Seed: Equatable, Sendable, Identifiable {
    public let id: Int
    public let name: String
    public init(id: Int, name: String) {
        self.id = id
        self.name = name
    }
}

public struct SeedReward: Sendable {
    public let seeds: [Seed]

    // 자리표시자 5종(실제 상품명으로 교체 가능).
    public static let defaultSeeds: [Seed] = [
        Seed(id: 0, name: "해바라기"),
        Seed(id: 1, name: "코스모스"),
        Seed(id: 2, name: "봉선화"),
        Seed(id: 3, name: "나팔꽃"),
        Seed(id: 4, name: "채송화"),
    ]

    public init(seeds: [Seed] = SeedReward.defaultSeeds) {
        precondition(!seeds.isEmpty, "씨앗은 1종 이상이어야 한다")
        self.seeds = seeds
    }

    /// 랜덤 1종 추첨. RNG 주입으로 결정적 테스트 가능.
    public func draw<G: RandomNumberGenerator>(using generator: inout G) -> Seed {
        seeds.randomElement(using: &generator)!
    }

    public func draw() -> Seed {
        var g = SystemRandomNumberGenerator()
        return draw(using: &g)
    }
}
