// 시그니처 비주얼 — "탄소 환산 씨앗 도감"(trash-t4i).
// 에코포인트(growth 0~1)만큼 줄기가 자라고 잎이 돋고, 점수가 높으면 꽃이 핀다.
// 막대사탕 보상은 가지에 열리는 '열매'로 시각화 → 순환자원·탄소·보상을 식물 성장 은유로 통합.
// 순수 SwiftUI Shape/Path(가벼움, 에셋 없음). 종이-컷아웃 느낌의 옅은 그림자.
import SwiftUI
import TrasherCore

struct SeedlingView: View {
    let category: WasteCategory
    let growth: Double            // 0...1 (eco_points/100)
    let fruits: Int              // 막대사탕 수 0..2 → 열매
    let showFruits: Bool         // 보상 공개 시 열매 등장

    @State private var grow: CGFloat = 0   // 줄기 성장 애니메이션(0→growth)

    private var g: CGFloat { CGFloat(max(0, min(1, growth))) }
    private var bloomColor: Color { Theme.category(category) }

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width, h = geo.size.height
            let stemTop = CGPoint(x: w * 0.5 - w * 0.06, y: h * 0.16)  // 꽃/열매가 프레임 안에 들도록 여백
            ZStack {
                pot(w: w, h: h)

                // 줄기 — Path를 grow까지 trim해 자라는 연출
                StemShape()
                    .trim(from: 0, to: grow)
                    .stroke(Theme.sprout, style: StrokeStyle(lineWidth: max(7, w * 0.045),
                                                             lineCap: .round, lineJoin: .round))
                    .shadow(color: .black.opacity(0.06), radius: 3, x: 1, y: 2)

                // 잎 — 성장 임계값에서 스케일 인
                leaf(at: CGPoint(x: w * 0.5 - w * 0.16, y: h * 0.58), angle: -32,
                     size: w * 0.30, threshold: 0.30)
                leaf(at: CGPoint(x: w * 0.5 + w * 0.15, y: h * 0.40), angle: 28,
                     size: w * 0.27, threshold: 0.55)

                // 꽃 — 점수 높을 때(>0.65) 줄기 끝에서 개화
                bloom(at: stemTop, unit: w)
                    .scaleEffect(bloomScale)
                    .opacity(grow > 0.65 ? 1 : 0)   // 줄기가 충분히 자란 뒤 개화(grow 연동)
                    .animation(.spring(response: 0.6, dampingFraction: 0.7), value: grow)

                // 열매(막대사탕) — 보상 공개 시 가지에 등장
                fruitCluster(top: stemTop, unit: w)
            }
            .onAppear {
                withAnimation(.easeOut(duration: 1.6)) { grow = g }
            }
        }
    }

    private var bloomScale: CGFloat {
        let p = (grow - 0.65) / 0.35   // 애니메이션 진행도(grow)에 연동
        return p <= 0 ? 0 : 0.6 + 0.4 * min(1, p)
    }

    // 화분
    private func pot(w: CGFloat, h: CGFloat) -> some View {
        PotShape()
            .fill(Theme.clay)
            .overlay(PotShape().stroke(.black.opacity(0.08), lineWidth: 2))
            .frame(width: w * 0.42, height: h * 0.20)
            .position(x: w * 0.5, y: h * 0.85)
            .shadow(color: .black.opacity(0.08), radius: 4, x: 1, y: 3)
    }

    // 잎 한 장(스케일 인)
    private func leaf(at p: CGPoint, angle: Double, size: CGFloat, threshold: CGFloat) -> some View {
        let appeared = grow >= threshold
        return LeafShape()
            .fill(Theme.sprout.opacity(0.92))
            .frame(width: size, height: size * 0.6)
            .rotationEffect(.degrees(angle))
            .scaleEffect(appeared ? 1 : 0.01, anchor: .leading)
            .opacity(appeared ? 1 : 0)
            .shadow(color: .black.opacity(0.05), radius: 2, x: 1, y: 1)
            .position(p)
            .animation(.spring(response: 0.5, dampingFraction: 0.6).delay(0.3), value: grow)
    }

    // 꽃(꽃잎 5 + 중심)
    private func bloom(at p: CGPoint, unit: CGFloat) -> some View {
        let petal = unit * 0.12
        return ZStack {
            ForEach(0..<5, id: \.self) { i in
                Circle().fill(bloomColor.opacity(0.9))
                    .frame(width: petal, height: petal)
                    .offset(y: -petal * 0.7)
                    .rotationEffect(.degrees(Double(i) / 5 * 360))
            }
            Circle().fill(category == .can ? Color.white : Theme.paper)
                .frame(width: petal * 0.7, height: petal * 0.7)
        }
        .position(p)
    }

    // 열매(막대사탕 느낌: 동그란 사탕 + 막대)
    private func fruitCluster(top: CGPoint, unit: CGFloat) -> some View {
        let r = unit * 0.085
        return ZStack {
            ForEach(0..<min(max(fruits, 0), 2), id: \.self) { i in
                let dx = (i == 0 ? -1.0 : 1.0) * unit * 0.16
                VStack(spacing: 0) {
                    Circle().fill(Theme.clay)
                        .overlay(Circle().stroke(.white.opacity(0.6), lineWidth: 2))
                        .frame(width: r * 2, height: r * 2)
                    Rectangle().fill(.white.opacity(0.75))
                        .frame(width: 2.5, height: r * 1.4)
                }
                .scaleEffect(showFruits ? 1 : 0.01)
                .opacity(showFruits ? 1 : 0)
                .position(x: top.x + dx, y: top.y + r * 1.2)
                .animation(.spring(response: 0.55, dampingFraction: 0.5).delay(Double(i) * 0.15), value: showFruits)
            }
        }
    }
}

// MARK: Shapes
private struct StemShape: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        let bottom = CGPoint(x: r.midX, y: r.maxY * 0.80)
        let top = CGPoint(x: r.midX - r.width * 0.06, y: r.minY + r.height * 0.16)
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

private struct PotShape: Shape {
    func path(in r: CGRect) -> Path {
        var p = Path()
        let inset = r.width * 0.12
        p.move(to: CGPoint(x: r.minX + inset, y: r.minY))
        p.addLine(to: CGPoint(x: r.maxX - inset, y: r.minY))
        p.addLine(to: CGPoint(x: r.maxX - inset * 1.8, y: r.maxY))
        p.addLine(to: CGPoint(x: r.minX + inset * 1.8, y: r.maxY))
        p.closeSubpath()
        return p
    }
}
