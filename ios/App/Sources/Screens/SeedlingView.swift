// 시그니처 비주얼 — "탄소 환산 씨앗 도감"(trash-t4i).
// 에코포인트(growth 0~1)만큼 줄기가 자라고 잎이 돋고, 점수가 높으면 꽃이 핀다.
// 막대사탕 보상은 가지에 열리는 '사탕 열매'로 시각화 → 순환자원·탄소·보상을 식물 성장 은유로 통합.
// 순수 SwiftUI Shape/Path(에셋 없음). 다크 캔버스용: 새싹/사탕이 발광하도록 글로우·그라데이션·하이라이트.
import SwiftUI
import TrasherCore

struct SeedlingView: View {
    let category: WasteCategory
    let growth: Double            // 0...1 (eco_points/100)
    let fruits: Int              // 막대사탕 수 0..2 → 사탕 열매
    let showFruits: Bool         // 보상 공개 시 열매 등장

    @State private var grow: CGFloat = 0   // 줄기 성장 애니메이션(0→growth)

    private var g: CGFloat { CGFloat(max(0, min(1, growth))) }
    private var bloomColor: Color { Theme.category(category) }

    // 화분(테라코타) — 다크 위에서 따뜻하게 떠오르는 자체 팔레트.
    private let potTop = Color(hex: 0xD9743C)
    private let potBottom = Color(hex: 0xA8512A)
    private let soil = Color(hex: 0x3A2A20)

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width, h = geo.size.height
            let stemTop = CGPoint(x: w * 0.5 - w * 0.05, y: h * 0.17)
            ZStack {
                // 0) 발광 — 식물 뒤로 번지는 초록 빛(다크 보태니컬 핵심)
                Circle()
                    .fill(RadialGradient(colors: [Theme.sprout.opacity(0.28), .clear],
                                         center: .center, startRadius: 4, endRadius: w * 0.55))
                    .frame(width: w, height: w)
                    .position(x: w * 0.5, y: h * 0.46)
                    .blur(radius: 8)

                pot(w: w, h: h)

                // 1) 줄기 — 그라데이션 스트로크를 grow까지 trim해 자라는 연출(밑동에 살짝 두꺼운 베이스)
                StemShape()
                    .trim(from: 0, to: grow)
                    .stroke(LinearGradient(colors: [Theme.sproutDeep, Theme.sprout],
                                           startPoint: .bottom, endPoint: .top),
                            style: StrokeStyle(lineWidth: max(8, w * 0.05), lineCap: .round, lineJoin: .round))
                    .shadow(color: Theme.sprout.opacity(0.35), radius: 6)

                // 2) 잎 — 성장 임계값에서 스케일 인(잎맥 포함)
                leaf(at: CGPoint(x: w * 0.5 - w * 0.17, y: h * 0.58), angle: -34,
                     size: w * 0.32, threshold: 0.28)
                leaf(at: CGPoint(x: w * 0.5 + w * 0.16, y: h * 0.41), angle: 30,
                     size: w * 0.28, threshold: 0.52)

                // 3) 꽃 — 점수 높을 때(>0.65) 줄기 끝에서 개화
                bloom(at: stemTop, unit: w)
                    .scaleEffect(bloomScale)
                    .opacity(grow > 0.65 ? 1 : 0)
                    .animation(.spring(response: 0.6, dampingFraction: 0.7), value: grow)

                // 4) 사탕 열매(막대사탕) — 보상 공개 시 가지에 등장
                fruitCluster(top: stemTop, unit: w)
            }
            .onAppear {
                withAnimation(.easeOut(duration: 1.6)) { grow = g }
            }
        }
    }

    private var bloomScale: CGFloat {
        let p = (grow - 0.65) / 0.35
        return p <= 0 ? 0 : 0.6 + 0.4 * min(1, p)
    }

    // 화분 — 본체(테라코타 그라데이션) + 림 밴드 + 흙. 종이컷 그림자.
    private func pot(w: CGFloat, h: CGFloat) -> some View {
        let pw = w * 0.46, ph = h * 0.22
        let cx = w * 0.5, cy = h * 0.85
        return ZStack {
            PotBodyShape()
                .fill(LinearGradient(colors: [potTop, potBottom], startPoint: .top, endPoint: .bottom))
                .overlay(PotBodyShape().stroke(.black.opacity(0.18), lineWidth: 2))
                .frame(width: pw, height: ph)
                .position(x: cx, y: cy)
            // 흙(본체 위 가장자리)
            Ellipse().fill(soil)
                .frame(width: pw * 0.86, height: ph * 0.16)
                .position(x: cx, y: cy - ph * 0.46)
            // 림 밴드(테두리 강조 + 상단 하이라이트)
            Capsule().fill(potTop)
                .overlay(Capsule().stroke(.white.opacity(0.18), lineWidth: 1.5))
                .frame(width: pw * 1.04, height: ph * 0.20)
                .position(x: cx, y: cy - ph * 0.44)
        }
        .shadow(color: .black.opacity(0.30), radius: 8, x: 0, y: 6)
    }

    // 잎 한 장(스케일 인) — 잎몸 그라데이션 + 중앙 잎맥.
    private func leaf(at p: CGPoint, angle: Double, size: CGFloat, threshold: CGFloat) -> some View {
        let appeared = grow >= threshold
        return ZStack {
            LeafShape().fill(LinearGradient(colors: [Theme.sprout, Theme.sproutDeep],
                                            startPoint: .topLeading, endPoint: .bottomTrailing))
            LeafShape().stroke(.black.opacity(0.10), lineWidth: 1)
            LeafVein().stroke(.white.opacity(0.35), style: StrokeStyle(lineWidth: 1.5, lineCap: .round))
        }
        .frame(width: size, height: size * 0.6)
        .rotationEffect(.degrees(angle))
        .scaleEffect(appeared ? 1 : 0.01, anchor: .leading)
        .opacity(appeared ? 1 : 0)
        .shadow(color: Theme.sprout.opacity(0.25), radius: 4)
        .position(p)
        .animation(.spring(response: 0.5, dampingFraction: 0.6).delay(0.3), value: grow)
    }

    // 꽃(둥근 꽃잎 5 + 발광 중심)
    private func bloom(at p: CGPoint, unit: CGFloat) -> some View {
        let petal = unit * 0.13
        return ZStack {
            ForEach(0..<5, id: \.self) { i in
                Capsule().fill(bloomColor)
                    .frame(width: petal * 0.8, height: petal * 1.5)
                    .offset(y: -petal * 0.85)
                    .rotationEffect(.degrees(Double(i) / 5 * 360))
            }
            Circle().fill(Theme.clay)
                .overlay(Circle().stroke(.white.opacity(0.7), lineWidth: 1.5))
                .frame(width: petal * 0.9, height: petal * 0.9)
                .shadow(color: Theme.clay.opacity(0.6), radius: 4)
        }
        .position(p)
    }

    // 사탕 열매(막대사탕) — 글로시 디스크 + 흰 스월 + 하이라이트 + 막대. 보상 공개 시 팝인.
    private func fruitCluster(top: CGPoint, unit: CGFloat) -> some View {
        let d = unit * 0.20
        return ZStack {
            ForEach(0..<min(max(fruits, 0), 2), id: \.self) { i in
                let dx = (i == 0 ? -1.0 : 1.0) * unit * 0.17
                lollipop(diameter: d, tilt: i == 0 ? -14 : 12)
                    .scaleEffect(showFruits ? 1 : 0.01)
                    .opacity(showFruits ? 1 : 0)
                    .position(x: top.x + dx, y: top.y + d * 0.55)
                    .animation(.spring(response: 0.55, dampingFraction: 0.5).delay(Double(i) * 0.15),
                               value: showFruits)
            }
        }
    }

    private func lollipop(diameter d: CGFloat, tilt: Double) -> some View {
        VStack(spacing: -d * 0.04) {
            // 막대(위로 가지에 연결)
            Capsule()
                .fill(LinearGradient(colors: [.white.opacity(0.95), Color(hex: 0xCBD5C9)],
                                     startPoint: .leading, endPoint: .trailing))
                .frame(width: d * 0.11, height: d * 0.5)
            // 사탕 디스크
            ZStack {
                Circle().fill(LinearGradient(colors: [Color(hex: 0xFF9F43), Theme.clay],
                                             startPoint: .topLeading, endPoint: .bottomTrailing))
                SwirlShape().stroke(.white.opacity(0.9),
                                    style: StrokeStyle(lineWidth: d * 0.06, lineCap: .round))
                    .clipShape(Circle())
                Circle().stroke(.white.opacity(0.5), lineWidth: 1.5)
                Ellipse().fill(.white.opacity(0.55))
                    .frame(width: d * 0.30, height: d * 0.18)
                    .offset(x: -d * 0.14, y: -d * 0.16)
            }
            .frame(width: d, height: d)
            .shadow(color: Theme.clay.opacity(0.5), radius: 6)
        }
        .rotationEffect(.degrees(tilt))
    }
}

// MARK: Shapes
private struct StemShape: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        let bottom = CGPoint(x: r.midX, y: r.maxY * 0.80)
        let top = CGPoint(x: r.midX - r.width * 0.05, y: r.minY + r.height * 0.17)
        let c1 = CGPoint(x: r.midX + r.width * 0.18, y: r.midY)
        let c2 = CGPoint(x: r.midX - r.width * 0.22, y: r.minY + r.height * 0.32)
        p.move(to: bottom)
        p.addCurve(to: top, control1: c1, control2: c2)
        return p
    }
}

private struct LeafShape: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: r.minX, y: r.midY))
        p.addQuadCurve(to: CGPoint(x: r.maxX, y: r.midY), control: CGPoint(x: r.midX, y: r.minY))
        p.addQuadCurve(to: CGPoint(x: r.minX, y: r.midY), control: CGPoint(x: r.midX, y: r.maxY))
        p.closeSubpath()
        return p
    }
}

// 잎맥 — 밑동에서 잎 끝으로 흐르는 중앙선.
private struct LeafVein: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        p.move(to: CGPoint(x: r.minX + r.width * 0.08, y: r.midY))
        p.addQuadCurve(to: CGPoint(x: r.maxX - r.width * 0.06, y: r.midY),
                       control: CGPoint(x: r.midX, y: r.minY + r.height * 0.34))
        return p
    }
}

// 화분 본체 — 둥근 밑모서리의 사다리꼴 화분.
private struct PotBodyShape: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        let inset = r.width * 0.10
        let radius = r.width * 0.10
        p.move(to: CGPoint(x: r.minX + inset, y: r.minY))
        p.addLine(to: CGPoint(x: r.maxX - inset, y: r.minY))
        p.addLine(to: CGPoint(x: r.maxX - inset * 1.9, y: r.maxY - radius))
        p.addQuadCurve(to: CGPoint(x: r.maxX - inset * 1.9 - radius, y: r.maxY),
                       control: CGPoint(x: r.maxX - inset * 1.9, y: r.maxY))
        p.addLine(to: CGPoint(x: r.minX + inset * 1.9 + radius, y: r.maxY))
        p.addQuadCurve(to: CGPoint(x: r.minX + inset * 1.9, y: r.maxY - radius),
                       control: CGPoint(x: r.minX + inset * 1.9, y: r.maxY))
        p.closeSubpath()
        return p
    }
}

// 막대사탕 스월 — 아르키메데스 나선.
private struct SwirlShape: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        let c = CGPoint(x: r.midX, y: r.midY)
        let maxR = min(r.width, r.height) / 2 * 0.92
        let turns = 2.6, steps = 90
        for i in 0...steps {
            let t = Double(i) / Double(steps)
            let ang = t * turns * 2 * .pi
            let rad = maxR * t
            let pt = CGPoint(x: c.x + CGFloat(cos(ang)) * CGFloat(rad),
                             y: c.y + CGFloat(sin(ang)) * CGFloat(rad))
            if i == 0 { p.move(to: pt) } else { p.addLine(to: pt) }
        }
        return p
    }
}
