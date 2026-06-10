// EcoReward 보상 산출 테스트 — 에코포인트→막대사탕 결정적 규칙. docs §4.6.
import XCTest
@testable import TrasherCore

final class EcoRewardTests: XCTestCase {
    func testNonRecyclableGivesNoLollipop() {
        let r = EcoReward(ecoPoints: 80, recyclable: false)
        XCTAssertEqual(r.lollipops, 0)
        XCTAssertEqual(r.ecoPoints, 0)   // 비재활용은 점수 0으로 정규화
    }

    func testZeroPointsGivesNoLollipop() {
        XCTAssertEqual(EcoReward(ecoPoints: 0, recyclable: true).lollipops, 0)
    }

    func testLowPointsGivesOneLollipop() {
        XCTAssertEqual(EcoReward(ecoPoints: 1, recyclable: true).lollipops, 1)
        XCTAssertEqual(EcoReward(ecoPoints: 49, recyclable: true).lollipops, 1)
    }

    func testHighPointsGivesTwoLollipops() {
        XCTAssertEqual(EcoReward(ecoPoints: 50, recyclable: true).lollipops, 2)
        XCTAssertEqual(EcoReward(ecoPoints: 100, recyclable: true).lollipops, 2)
    }

    func testOtherButRecyclableStillRewards() {
        // "기타"라도 재활용 가능하면 보상 — eco 정보만으로 산출(카테고리 무관).
        let r = EcoReward(ecoPoints: 30, recyclable: true)
        XCTAssertEqual(r.lollipops, 1)
        XCTAssertEqual(r.ecoPoints, 30)
    }

    func testFromRawUsesEcoFields() {
        let raw = RawClassification(
            label: "pet", confidence: 0.95, description: "팁", ecoPoints: 60, recyclable: true
        )
        XCTAssertEqual(EcoReward(raw: raw).lollipops, 2)
    }

    func testFromRawMissingEcoIsSafeNoReward() {
        let raw = RawClassification(label: "pet", confidence: 0.95)
        XCTAssertEqual(EcoReward(raw: raw).lollipops, 0)
    }

    func testFallbackNoneHasNoReward() {
        XCTAssertEqual(EcoReward.none.lollipops, 0)
        XCTAssertFalse(EcoReward.none.recyclable)
    }

    func testNegativePointsClampedToZero() {
        XCTAssertEqual(EcoReward(ecoPoints: -5, recyclable: true).ecoPoints, 0)
        XCTAssertEqual(EcoReward(ecoPoints: -5, recyclable: true).lollipops, 0)
    }

    func testPointsClampedToHundred() {
        // Pi schema와 동일하게 상한 100(링 게이지 100% 초과 방지).
        XCTAssertEqual(EcoReward(ecoPoints: 150, recyclable: true).ecoPoints, 100)
        XCTAssertEqual(EcoReward(ecoPoints: 150, recyclable: true).lollipops, 2)
    }

    func testCO2GramsEstimate() {
        // 탄소절감 CO₂ 추정(표시 전용) — 60점 ≈ 120g(2g/점).
        XCTAssertEqual(EcoReward(ecoPoints: 60, recyclable: true).co2Grams, 120)
        XCTAssertEqual(EcoReward(ecoPoints: 100, recyclable: true).co2Grams, 200)
    }

    func testCO2GramsZeroWhenNoReward() {
        // 비재활용/0점은 점수가 0으로 정규화되므로 CO₂도 0g.
        XCTAssertEqual(EcoReward(ecoPoints: 80, recyclable: false).co2Grams, 0)
        XCTAssertEqual(EcoReward(ecoPoints: 0, recyclable: true).co2Grams, 0)
    }
}
