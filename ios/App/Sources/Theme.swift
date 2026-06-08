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
    // 팔레트
    static let paper = Color(hex: 0xF2ECDD)   // 따뜻한 크림(흙빛)
    static let paperDeep = Color(hex: 0xE7DEC8)
    static let ink = Color(hex: 0x1B2A1F)     // 딥 포레스트
    static let inkSoft = Color(hex: 0x4A5A4C)
    static let sprout = Color(hex: 0x6FBF3F)  // 새싹(주 액센트)
    static let clay = Color(hex: 0xE07A3F)    // 클레이(에너지 액센트)

    // 카테고리 색
    static let petBlue = Color(hex: 0x2D9CDB)
    static let canAmber = Color(hex: 0xE0A92F)
    static let otherStone = Color(hex: 0x8A8170)

    static func category(_ c: WasteCategory) -> Color {
        switch c {
        case .pet: return petBlue
        case .can: return canAmber
        case .other: return otherStone
        }
    }

    // 타이포 스케일(대형 한글, system black/rounded — 추후 Pretendard 번들 가능)
    static func display(_ size: CGFloat = 96) -> Font { .system(size: size, weight: .black, design: .rounded) }
    static func title(_ size: CGFloat = 56) -> Font { .system(size: size, weight: .heavy, design: .rounded) }
    static func body(_ size: CGFloat = 28) -> Font { .system(size: size, weight: .semibold, design: .rounded) }
    static func caption(_ size: CGFloat = 20) -> Font { .system(size: size, weight: .medium, design: .rounded) }
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
