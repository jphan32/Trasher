// 4단계 진행 스테퍼 — 촬영 → AI 인식 → 이동 → 분류.
// "씨앗이 자라는 여정": 덩굴로 이어진 노드. 완료=체크, 현재=펄스 새싹, 대기=흐린 윤곽.
import SwiftUI
import TrasherCore

/// AI 재활용 팁 박스(💡) — processing/reward 공용. 다크 면 위 정의된 카드 + 새싹 보더.
struct TipBox: View {
    let text: String
    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            Text("💡").font(.system(size: 30))
            Text(text)
                .font(Theme.body(24))
                .foregroundStyle(Theme.ink)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(20)
        .frame(maxWidth: 640)
        .background(Theme.surfaceHi, in: RoundedRectangle(cornerRadius: 20))
        .overlay(RoundedRectangle(cornerRadius: 20).stroke(Theme.sprout.opacity(0.35), lineWidth: 1.5))
    }
}

struct StepperView: View {
    let current: CycleStep
    var compact: Bool = false
    @State private var pulse = false

    private var nodeSize: CGFloat { compact ? 44 : 68 }
    private var iconSize: CGFloat { compact ? 18 : 28 }

    var body: some View {
        HStack(spacing: 0) {
            ForEach(Array(CycleStep.allCases.enumerated()), id: \.offset) { index, step in
                node(step)
                if index < CycleStep.allCases.count - 1 {
                    connector(done: step.rawValue < current.rawValue)
                }
            }
        }
        .onAppear { pulse = true }
    }

    @ViewBuilder private func node(_ step: CycleStep) -> some View {
        let done = step.rawValue < current.rawValue
        let active = step == current
        VStack(spacing: compact ? 6 : 12) {
            ZStack {
                if active {  // 펄스 링
                    Circle().stroke(Theme.sprout.opacity(0.35), lineWidth: 5)
                        .frame(width: nodeSize + 18, height: nodeSize + 18)
                        .scaleEffect(pulse ? 1.12 : 0.9)
                        .opacity(pulse ? 0 : 0.8)
                        .animation(.easeOut(duration: 1.4).repeatForever(autoreverses: false), value: pulse)
                }
                Circle()
                    .fill(done || active ? Theme.sprout : Color.clear)
                    .overlay(Circle().stroke(done || active ? Color.clear : Theme.line, lineWidth: 4))
                    .frame(width: nodeSize, height: nodeSize)
                    .shadow(color: done || active ? Theme.sprout.opacity(0.45) : .clear, radius: 6)
                Image(systemName: done ? "checkmark" : step.symbol)
                    .font(.system(size: iconSize, weight: .black))
                    .foregroundStyle(done || active ? Theme.canvas : Theme.inkSoft)
            }
            if !compact {
                Text(step.label)
                    .font(active ? Theme.body(22) : Theme.caption(20))
                    .foregroundStyle(active ? Theme.ink : (done ? Theme.inkSoft : Theme.inkSoft.opacity(0.6)))
            }
        }
        .scaleEffect(active ? 1.0 : 0.96)
        .animation(.spring(response: 0.4, dampingFraction: 0.7), value: current)
    }

    private func connector(done: Bool) -> some View {
        RoundedRectangle(cornerRadius: 2)
            .fill(done ? Theme.sprout : Theme.paperDeep)
            .frame(height: 4)
            .frame(maxWidth: .infinity)
            .padding(.bottom, compact ? 0 : 36)  // 라벨 높이만큼 위로 정렬
            .animation(.easeInOut(duration: 0.4), value: done)
    }
}
