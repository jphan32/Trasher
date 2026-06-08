// 씨앗 추첨 테스트 — 결정적 RNG 주입.
import XCTest
@testable import TrasherCore

private struct SeededGen: RandomNumberGenerator {
    var state: UInt64
    init(seed: UInt64) { state = seed }
    mutating func next() -> UInt64 {
        state = state &* 6364136223846793005 &+ 1442695040888963407
        return state
    }
}

final class SeedRewardTests: XCTestCase {
    func testDefaultHasFiveSeeds() {
        XCTAssertEqual(SeedReward().seeds.count, 5)
        XCTAssertEqual(Set(SeedReward().seeds.map(\.id)).count, 5)
    }

    func testDrawIsDeterministicForSeed() {
        let reward = SeedReward()
        var g1 = SeededGen(seed: 42), g2 = SeededGen(seed: 42)
        XCTAssertEqual(reward.draw(using: &g1), reward.draw(using: &g2))
    }

    func testDrawAlwaysFromSeeds() {
        let reward = SeedReward()
        var g = SeededGen(seed: 7)
        for _ in 0..<50 {
            XCTAssertTrue(reward.seeds.contains(reward.draw(using: &g)))
        }
    }
}
