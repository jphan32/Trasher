// 결과 + 보상 화면(가로 2-컬럼). 좌: 사진+카테고리+팁 / 우: 에코링+탄소절감+막대사탕.
// 무터치 자동 진행(참가자 터치 없음): 카운트업→단계적 사탕 공개→리셋 힌트→자동 복귀.
// 보상 모델 docs/protocol.md §4.6. 에코포인트/CO₂는 EcoReward(SessionCoordinator.onEcoReward).
import SwiftUI
import TrasherCore

struct RewardView: View {
    let model: ScreenModel
    @EnvironmentObject var app: AppModel
    @State private var stamp = false
    @State private var revealed = false
    @State private var showResetHint = false       // 리셋 임박(가족 사진 보호, NNg 권장)
    @State private var displayedPoints = 0
    @State private var countTask: Task<Void, Never>?
    @State private var autoTask: Task<Void, Never>?   // 무터치 자동 진행(리빌+복귀)

    private var category: WasteCategory { model.category ?? .other }
    private var reward: EcoReward { app.ecoReward ?? .none }
    private var ringColor: Color { reward.recyclable ? Theme.sprout : Theme.otherBark }

    var body: some View {
        VStack(spacing: 16) {
            StepperView(current: .sort, compact: true)  // 여정 완료
                .padding(.top, 10).padding(.horizontal, 60)

            HStack(alignment: .center, spacing: 36) {
                leftColumn
                ecoCard
            }
            .padding(.horizontal, 28)

            Spacer(minLength: 0)

            if showResetHint {
                Text("곧 처음 화면으로 돌아가요")
                    .font(Theme.caption(20)).foregroundStyle(Theme.inkSoft)
                    .padding(.bottom, 10).transition(.opacity)
            }
        }
        .padding(.vertical, 22)
        .onAppear {
            stamp = true
            startCountUp(to: reward.ecoPoints)
            startAutoSequence()   // 참가자 무터치: 자동 사탕 공개 + 자동 어트랙트 복귀
        }
        .onDisappear { countTask?.cancel(); autoTask?.cancel() }
    }

    // MARK: 좌측 — 사진 + 카테고리 배지 + 재활용 팁
    private var leftColumn: some View {
        VStack(alignment: .leading, spacing: 18) {
            if let photo = app.photo {
                Image(uiImage: photo).resizable().scaledToFill()
                    .frame(width: 236, height: 236).clipShape(RoundedRectangle(cornerRadius: 24))
                    .overlay(RoundedRectangle(cornerRadius: 24).stroke(Theme.paperDeep, lineWidth: 3))
            }
            HStack(alignment: .center, spacing: 14) {
                Text(category.displayName)
                    .font(Theme.display(60)).foregroundStyle(.white)
                    .padding(.horizontal, 30).padding(.vertical, 12)
                    .background(Theme.category(category), in: RoundedRectangle(cornerRadius: 22))
                    .scaleEffect(stamp ? 1 : 0.6)
                    .rotationEffect(.degrees(stamp ? 0 : -8))
                    .animation(.spring(response: 0.5, dampingFraction: 0.55), value: stamp)
                Text("으로\n분류했어요").font(Theme.body(24)).foregroundStyle(Theme.inkSoft)
            }
            if let tip = app.tip, !tip.isEmpty {
                TipBox(text: tip)
            }
        }
        .frame(maxWidth: 440, alignment: .leading)
    }

    // MARK: 우측 — 에코포인트 링 + 탄소절감 + 보상 리빌
    private var ecoCard: some View {
        VStack(spacing: 16) {
            ZStack {
                Circle().stroke(Theme.paperDeep, lineWidth: 13)
                Circle()
                    .trim(from: 0, to: stamp ? CGFloat(reward.ecoPoints) / 100 : 0)
                    .stroke(ringColor, style: StrokeStyle(lineWidth: 13, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                    .animation(.easeOut(duration: 1.0), value: stamp)
                VStack(spacing: 0) {
                    Text("🌍").font(.system(size: 28))
                    Text("\(displayedPoints)").font(Theme.display(58)).foregroundStyle(Theme.ink)
                    Text("에코포인트").font(Theme.caption(16)).foregroundStyle(Theme.inkSoft)
                }
            }
            .frame(width: 188, height: 188)

            // 탄소절감 CO₂(에코포인트 환산, 표시 전용 근사) + 소나무 체감 비유
            if reward.ecoPoints > 0 {
                VStack(spacing: 4) {
                    Text("탄소절감 약 \(reward.co2Grams)g CO₂")
                        .font(Theme.title(28)).foregroundStyle(ringColor)
                    Text(treeComparison)
                        .font(Theme.caption(18)).foregroundStyle(Theme.inkSoft)
                        .multilineTextAlignment(.center)
                }
            }

            Text(ecoHeadline)
                .font(Theme.body(22)).foregroundStyle(Theme.inkSoft)
                .multilineTextAlignment(.center)

            rewardReveal
        }
        .padding(26)
        .frame(maxWidth: 480)
        .background(.white.opacity(0.5), in: RoundedRectangle(cornerRadius: 32))
    }

    private var ecoHeadline: String {
        reward.lollipops > 0
            ? "탄소절감에 기여했어요! 막대사탕을 받아 가세요"
            : "재활용이 어려운 쓰레기라 에코포인트가 없어요"
    }

    // 소나무 1그루 흡수 환산(체감 비유). 48시간↑은 '일'로 표기.
    private var treeComparison: String {
        let h = reward.treeHours
        if h >= 48 { return "🌲 소나무 한 그루가 약 \(Int((Double(h) / 24).rounded()))일 마시는 양" }
        return "🌲 소나무 한 그루가 약 \(h)시간 마시는 양"
    }

    // MARK: 보상 리빌(무터치) — 단계적 자동 공개. 참가자 터치 없음(startAutoSequence).
    @ViewBuilder private var rewardReveal: some View {
        if reward.lollipops == 0 {
            VStack(spacing: 12) {
                Text("🗑️").font(.system(size: 56))
                Text("재활용 가능한 쓰레기를 넣으면\n막대사탕을 받을 수 있어요")
                    .font(Theme.body(20)).foregroundStyle(Theme.inkSoft)
                    .multilineTextAlignment(.center)
            }
            .transition(.opacity)
        } else if !revealed {
            // 자동 공개 대기 — 선물 상자(터치 불필요, 곧 자동으로 열림)
            Text("🎁").font(.system(size: 76))
                .scaleEffect(stamp ? 1 : 0.6)
                .transition(.opacity)
        } else {
            VStack(spacing: 14) {
                lollipopBurst
                Text("막대사탕 \(reward.lollipops)개 당첨!")
                    .font(Theme.title(36)).foregroundStyle(Theme.clay)
            }
            .transition(.scale(scale: 0.85).combined(with: .opacity))
        }
    }

    // MARK: 사탕 당첨 이펙트(스프링 등장 + 스파클)
    private var lollipopBurst: some View {
        ZStack {
            SparkleBurst()
            HStack(spacing: 18) {
                ForEach(0..<reward.lollipops, id: \.self) { i in
                    Text("🍭")
                        .font(.system(size: 92))
                        .rotationEffect(.degrees(revealed ? (i == 0 ? -10 : 10) : -45))
                        .scaleEffect(revealed ? 1 : 0.2)
                        .animation(
                            .spring(response: 0.55, dampingFraction: 0.5).delay(Double(i) * 0.18),
                            value: revealed
                        )
                }
            }
        }
        .frame(height: 128)
    }

    // 무터치 단계적 자동 시퀀스(NNg 키오스크 페이싱): 점수 인지 → 사탕 공개 → 리셋 힌트 → 복귀.
    // 당첨 ~11초 / 미당첨 ~8초. 참가자는 일절 터치하지 않는다. 운영자는 RootView 숨김 제스처만.
    private func startAutoSequence() {
        autoTask?.cancel()
        autoTask = Task { @MainActor in
            let won = reward.lollipops > 0
            // 1) 점수·탄소 인지 시간(카운트업 ~1s + 여유) — 사탕은 숨겨 시선 분산 방지
            try? await Task.sleep(nanoseconds: 2_500_000_000)
            if Task.isCancelled { return }
            if won {
                withAnimation(.spring(response: 0.6, dampingFraction: 0.6)) { revealed = true }
            }
            // 2) 연출 유지(당첨은 더 길게 — 사탕 수령 시간)
            try? await Task.sleep(nanoseconds: won ? 6_500_000_000 : 3_500_000_000)
            if Task.isCancelled { return }
            // 3) 리셋 임박 힌트(사진 촬영 보호) 후 복귀
            withAnimation(.easeIn(duration: 0.3)) { showResetHint = true }
            try? await Task.sleep(nanoseconds: 2_000_000_000)
            if Task.isCancelled { return }
            app.finishReward()
        }
    }

    // 에코포인트 카운트업 애니메이션(0 → 목표).
    private func startCountUp(to target: Int) {
        guard target > 0 else { displayedPoints = 0; return }
        countTask?.cancel()
        countTask = Task { @MainActor in
            let steps = min(target, 35)
            for i in 0...steps {
                if Task.isCancelled { return }
                displayedPoints = Int((Double(target) * Double(i) / Double(steps)).rounded())
                try? await Task.sleep(nanoseconds: 28_000_000)
            }
            displayedPoints = target
        }
    }
}

/// 당첨 순간 방사형 스파클 버스트(등장 시 1회). 키오스크용 가벼운 이펙트.
private struct SparkleBurst: View {
    @State private var go = false
    private let symbols = ["✨", "🎉", "⭐️", "🌟", "💫"]
    private let count = 14

    var body: some View {
        ZStack {
            ForEach(0..<count, id: \.self) { i in
                let angle = Double(i) / Double(count) * 2 * .pi
                let mag: CGFloat = 120 + CGFloat(i % 4) * 30
                Text(symbols[i % symbols.count])
                    .font(.system(size: 24 + CGFloat(i % 3) * 8))
                    .offset(x: go ? cos(angle) * mag : 0, y: go ? sin(angle) * mag : 0)
                    .opacity(go ? 0 : 1)
                    .scaleEffect(go ? 0.4 : 1)
            }
        }
        .onAppear { withAnimation(.easeOut(duration: 1.1)) { go = true } }
        .allowsHitTesting(false)
    }
}
