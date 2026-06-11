// 디자인 시스템 — 딥 포레스트 "다크 보태니컬" 컨셉.
// 밤의 숲 캔버스 위에서 새싹·열매가 발광하듯 살아난다. 따뜻한 크림(구 #F5F2EB)은 폐기.
// 대형 한글 타이포(키오스크 1~2m). 대비: 본문 14:1, 보조 7:1, 액센트 8:1+ (WCAG AAA 지향).
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
    // 캔버스/면 — 깊은 숲 그린. 라디얼 글로우로 중앙에 빛이 고이는 느낌.
    static let canvas = Color(hex: 0x0E1A12)     // 베이스(밤의 숲)
    static let canvasGlow = Color(hex: 0x1C3A26) // 중앙 발광(PaperBackground 라디얼)
    static let surface = Color(hex: 0x16271C)    // 카드 면
    static let surfaceHi = Color(hex: 0x21392A)  // 상승 면/칩/팁박스
    static let line = Color(hex: 0x335040)       // 보더·커넥터·대기 윤곽

    // 텍스트
    static let ink = Color(hex: 0xF1F6F1)        // 본문(near-white, 14:1)
    static let inkSoft = Color(hex: 0xA6BBAC)    // 보조(세이지, 7.2:1)

    // 액센트
    static let sprout = Color(hex: 0x46D27E)     // 발광 그린(주 에코 액센트, 9:1)
    static let sproutDeep = Color(hex: 0x1F6B3F) // 잎·줄기 그라데이션 하단
    static let clay = Color(hex: 0xF2B43C)       // 허니 골드(보상·사탕·에너지, 11:1)
    static let danger = Color(hex: 0xE5484D)     // 위험·오류·E-STOP(흰 텍스트 4.5:1)

    // 카테고리 색 — 비비드 칩 + 어두운 텍스트(onCategory)로 다크 위 분리도↑(스티커 룩).
    // 환경부 규약 정렬(클리어PET=황색 / 캔=회색 / 기타=바크).
    static let petGold = Color(hex: 0xE0A92E)    // 페트=황금
    static let canSlate = Color(hex: 0x93A1AD)   // 캔=라이트 슬레이트
    static let otherBark = Color(hex: 0xCC9070)  // 기타=웜 바크
    static let onCategory = canvas               // 카테고리 칩 위 텍스트(어두움)

    static func category(_ c: WasteCategory) -> Color {
        switch c {
        case .pet: return petGold
        case .can: return canSlate
        case .other: return otherBark
        }
    }

    // 하위호환 별칭(과거 paper/paperDeep 참조 지점 보호). 다크 등가로 매핑.
    static let paper = canvas
    static let paperDeep = line

    // 타이포 — Pretendard 번들(OFL). 한글/영문 통일·키오스크 가독성.
    // (등록 실패 시 .custom은 시스템 폰트로 안전 폴백 — 크래시 없음.)
    static func display(_ size: CGFloat = 96) -> Font { .custom("Pretendard-Black", size: size) }
    static func title(_ size: CGFloat = 56) -> Font { .custom("Pretendard-Bold", size: size) }
    static func body(_ size: CGFloat = 28) -> Font { .custom("Pretendard-SemiBold", size: size) }
    static func caption(_ size: CGFloat = 20) -> Font { .custom("Pretendard-Medium", size: size) }
}

/// 밤의 숲 배경 — 중앙 발광 + 상단 림라이트 + 하단 비네팅으로 깊이를 만든다.
struct PaperBackground: View {
    var tint: Color = Theme.canvas
    var body: some View {
        ZStack {
            tint
            // 중앙으로 빛이 고이는 발광(시선 집중)
            RadialGradient(colors: [Theme.canvasGlow.opacity(0.55), .clear],
                           center: .center, startRadius: 60, endRadius: 760)
            // 상단 미세 림라이트(차가운 그린)
            LinearGradient(colors: [Theme.sprout.opacity(0.06), .clear],
                           startPoint: .top, endPoint: .center)
            // 가장자리 비네팅(키오스크 몰입)
            RadialGradient(colors: [.clear, .black.opacity(0.38)],
                           center: .center, startRadius: 440, endRadius: 1150)
        }
        .ignoresSafeArea()
    }
}
