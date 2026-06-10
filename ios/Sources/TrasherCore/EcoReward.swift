// 보상 모델 — 탄소절감 에코포인트 → 막대사탕 1~2개. docs/protocol.md §4.6.
//
// 씨앗 랜덤 추첨(SeedReward)을 대체한다. 랜덤이 아니라 Gemini가 산출한 eco_points에서
// 결정적으로 사탕 수를 도출한다(테스트 가능). "기타"라도 recyclable=true면 보상 대상이고,
// 재활용 불가 일반 쓰레기(recyclable=false)는 사탕 0개(굿즈 없음).

public struct EcoReward: Equatable, Sendable {
    public let ecoPoints: Int     // 탄소절감 에코포인트(0~100, 표시·산출용)
    public let recyclable: Bool   // 재활용 가능 여부
    public let lollipops: Int     // 지급 막대사탕 수: 0 / 1 / 2

    /// 사탕 2개 임계값(이상이면 2개). 튜닝 대상. docs §4.6.
    public static let twoLollipopThreshold = 50
    /// 에코포인트 상한(Pi schema와 동일). 표시·링 게이지가 100% 넘지 않게 클램프.
    public static let maxPoints = 100

    /// eco_points → CO₂ 절감량(g) 추정 환산계수(표시 전용 근사). 60점 ≈ 120g(2g/점).
    /// 실측이 아니라 참가자 체감용 근사치다. docs §4.6.
    public static let gramsCO2PerPoint = 2.0

    /// 표시용 CO₂ 절감량(g) 추정치. 비재활용/0점은 0g(ecoPoints가 이미 정규화됨).
    public var co2Grams: Int { Int((Double(ecoPoints) * Self.gramsCO2PerPoint).rounded()) }

    /// eco_points/recyclable로부터 보상을 결정적으로 산출.
    /// - 재활용 불가 또는 0점 → 0개
    /// - 0 < 점수 < 임계값 → 1개
    /// - 점수 >= 임계값 → 2개
    public init(ecoPoints: Int, recyclable: Bool) {
        // 비재활용은 점수 0으로 정규화(보상 일관성). 0~100 클램프(Pi schema와 동일).
        let points = recyclable ? min(Self.maxPoints, max(0, ecoPoints)) : 0
        self.ecoPoints = points
        self.recyclable = recyclable
        if points <= 0 {
            self.lollipops = 0
        } else if points < Self.twoLollipopThreshold {
            self.lollipops = 1
        } else {
            self.lollipops = 2
        }
    }

    /// 원시 분류로부터 보상 산출. eco 필드가 없으면(구버전/일부 mock) 안전하게 보상 없음.
    public init(raw: RawClassification) {
        self.init(ecoPoints: raw.ecoPoints ?? 0, recyclable: raw.recyclable ?? false)
    }

    /// 폴백(분류 실패/타임아웃, §6) — 보상 없음.
    public static let none = EcoReward(ecoPoints: 0, recyclable: false)
}
