// 디자인 시스템 — 유기적 에디토리얼-식물 컨셉.
// 따뜻한 크림 페이퍼 + 딥 포레스트 잉크 + 비비드 새싹/클레이. 대형 한글 타이포(키오스크).
import SwiftUI
import TrasherCore

extension Color {
    init(hex: UInt) {
        self.init(.sRGB,
                  red: Double((hex >> 16) & 0xFF) / 255,
                  green: Double((hex >> 8) & 0xFF) / 255,
                  blue: Double(hex & 0xFF) / 255,
                  opacity: 1)
    }
}

enum Theme {
    // 팔레트 — WCAG 정비 + 한국 환경부 분리배출 색 규약 정렬(M4, trash-79k/q52).
    // 대비율은 paper 기준(키오스크 1~2m·조명 변화 대응). 출처: 환경부 분리배출 지침, WCAG 2.2.
    static let paper = Color(hex: 0xF5F2EB)   // 따뜻한 크림(흙빛) 베이스
    static let paperDeep = Color(hex: 0xE6DEC9) // 카드/보더/비네팅
    static let ink = Color(hex: 0x1F2421)     // 딥 포레스트-차콜(본문, 15.1:1)
    static let inkSoft = Color(hex: 0x566259) // 세이지(보조 텍스트, 5.8:1)
    static let sprout = Color(hex: 0x2A5A3B)  // 포레스트 그린(주 에코 액센트, 7.2:1; 흰 텍스트 8.1:1)
    static let clay = Color(hex: 0xC25A28)    // 테라코타(에너지/보상 액센트). 텍스트/버튼 모두 흰색 대비 4.4:1

    // 카테고리 색 — 환경부 규약(클리어PET=황색 / 캔=회색) + 흰 텍스트 대비≥4:1 보장.
    static let petGold = Color(hex: 0xAC7300)   // 페트=황색 계열(흰 텍스트 4.06:1)
    static let canSlate = Color(hex: 0x4F5D65)  // 캔=회색 계열(흰 텍스트 6.77:1)
    static let otherBark = Color(hex: 0x8E5E50) // 기타=바크 브라운(흰 텍스트 5.4:1)

    static func category(_ c: WasteCategory) -> Color {
        switch c {
        case .pet: return petGold
        case .can: return canSlate
        case .other: return otherBark
        }
    }

    // 타이포 — Pretendard 번들(OFL, trash-7kb). SF Rounded는 한글 글리프가 없어 SD Gothic Neo로
    // 폴백돼 영문/한글이 불일치했다. Pretendard로 통일해 키오스크 한글 가독성을 높인다.
    // (등록 실패 시 .custom은 시스템 폰트로 안전 폴백 — 크래시 없음.)
    static func display(_ size: CGFloat = 96) -> Font { .custom("Pretendard-Black", size: size) }
    static func title(_ size: CGFloat = 56) -> Font { .custom("Pretendard-Bold", size: size) }
    static func body(_ size: CGFloat = 28) -> Font { .custom("Pretendard-SemiBold", size: size) }
    static func caption(_ size: CGFloat = 20) -> Font { .custom("Pretendard-Medium", size: size) }
}

/// 종이 질감 배경 + 부드러운 비네팅.
struct PaperBackground: View {
    var tint: Color = Theme.paper
    var body: some View {
        ZStack {
            tint
            RadialGradient(colors: [Theme.paperDeep.opacity(0.0), Theme.paperDeep.opacity(0.5)],
                           center: .center, startRadius: 200, endRadius: 1200)
        }
        .ignoresSafeArea()
    }
}
