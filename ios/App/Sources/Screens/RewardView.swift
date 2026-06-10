// 결과 + 보상 화면. 카테고리 배지 → 탄소절감 에코포인트 → 막대사탕 1~2개 당첨 이펙트.
// 보상 모델 docs/protocol.md §4.6. 에코포인트는 EcoReward(SessionCoordinator.onEcoReward)에서.
import SwiftUI
import TrasherCore

struct RewardView: View {
    let model: ScreenModel
    @EnvironmentObject var app: AppModel
    @State private var stamp = false
    @State private var revealed = false
    @State private var displayedPoints = 0
    @State private var countTask: Task<Void, Never>?
    @State private var autoTask: Task<Void, Never>?   // 무터치 자동 진행(리빌+복귀)

    private var category: WasteCategory { model.category ?? .other }
    private var reward: EcoReward { app.ecoReward ?? .none }
    private var ringColor: Color { reward.recyclable ? Theme.sprout : Theme.otherStone }

    var body: some View {
        VStack(spacing: 24) {
            StepperView(current: .sort, compact: true)  // 여정 완료
                .padding(.top, 14).padding(.horizontal, 60)

            resultHeader

            if let tip = app.tip, !tip.isEmpty {
                TipBox(text: tip).padding(.horizontal, 32)
            }

            ecoCard

            Spacer(minLength: 0)
        }
        .padding(32)
        .onAppear {
            stamp = true
            startCountUp(to: reward.ecoPoints)
            startAutoSequence()   // 참가자 무터치: 자동 사탕 공개 + 자동 어트랙트 복귀
        }
        .onDisappear { countTask?.cancel(); autoTask?.cancel() }
    }

    // MARK: 결과 헤더(사진 + 카테고리 배지)
    private var resultHeader: some View {
        HStack(spacing: 22) {
            if let photo = app.photo {
                Image(uiImage: photo).resizable().scaledToFill()
                    .frame(width: 120, height: 120).clipShape(RoundedRectangle(cornerRadius: 22))
                    .overlay(RoundedRectangle(cornerRadius: 22).stroke(Theme.paperDeep, lineWidth: 3))
            }
            VStack(alignment: .leading, spacing: 6) {
                Text(category.displayName)
                    .font(Theme.display(72))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 40).padding(.vertical, 16)
                    .background(Theme.category(category), in: RoundedRectangle(cornerRadius: 28))
                    .scaleEffect(stamp ? 1 : 0.6)
                    .rotationEffect(.degrees(stamp ? 0 : -8))
                    .animation(.spring(response: 0.5, dampingFraction: 0.55), value: stamp)
                Text("으로 분류했어요").font(Theme.body(26)).foregroundStyle(Theme.inkSoft)
            }
        }
    }

    // MARK: 에코포인트 카드 + 보상 리빌
    private var ecoCard: some View {
        VStack(spacing: 20) {
            ZStack {
                Circle().stroke(Theme.paperDeep, lineWidth: 14)
                Circle()
                    .trim(from: 0, to: stamp ? CGFloat(reward.ecoPoints) / 100 : 0)
                    .stroke(ringColor, style: StrokeStyle(lineWidth: 14, lineCap: .round))
                    .rotationEffect(.degrees(-90))
                    .animation(.easeOut(duration: 1.0), value: stamp)
                VStack(spacing: 0) {
                    Text("🌍").font(.system(size: 30))
                    Text("\(displayedPoints)").font(Theme.display(68)).foregroundStyle(Theme.ink)
                    Text("에코포인트").font(Theme.caption(18)).foregroundStyle(Theme.inkSoft)
                }
            }
            .frame(width: 210, height: 210)

            // 탄소절감 CO₂ 추정 병기(에코포인트 환산, 표시 전용 근사)
            if reward.ecoPoints > 0 {
                VStack(spacing: 2) {
                    Text("탄소절감 약").font(Theme.caption(18)).foregroundStyle(Theme.inkSoft)
                    Text("\(reward.co2Grams)g CO₂").font(Theme.title(34)).foregroundStyle(ringColor)
                }
            }

            Text(ecoHeadline)
                .font(Theme.body(24)).foregroundStyle(Theme.inkSoft)
                .multilineTextAlignment(.center)

            rewardReveal
        }
        .padding(28)
        .frame(maxWidth: 680)
        .background(.white.opacity(0.45), in: RoundedRectangle(cornerRadius: 32))
    }

    private var ecoHeadline: String {
        reward.lollipops > 0
            ? "탄소절감에 기여했어요! 막대사탕을 받아 가세요"
            : "재활용이 어려운 쓰레기라 에코포인트가 없어요"
    }

    // MARK: 보상 리빌(무터치) — 자동 공개/복귀. 참가자 터치 없음(startAutoSequence).
    @ViewBuilder private var rewardReveal: some View {
        if reward.lollipops == 0 {
            VStack(spacing: 14) {
                Text("🗑️").font(.system(size: 64))
                Text("재활용 가능한 쓰레기를 넣으면\n막대사탕을 받을 수 있어요")
                    .font(Theme.body(22)).foregroundStyle(Theme.inkSoft)
                    .multilineTextAlignment(.center)
            }
            .transition(.opacity)
        } else if !revealed {
            // 자동 공개 대기 — 선물 상자(터치 불필요, 곧 자동으로 열림)
            Text("🎁").font(.system(size: 88))
                .scaleEffect(stamp ? 1 : 0.6)
                .transition(.opacity)
        } else {
            VStack(spacing: 18) {
                lollipopBurst
                Text("막대사탕 \(reward.lollipops)개 당첨!")
                    .font(Theme.title(40)).foregroundStyle(Theme.clay)
            }
            .transition(.scale(scale: 0.85).combined(with: .opacity))
        }
    }

    // MARK: 사탕 당첨 이펙트(스프링 등장 + 스파클)
    private var lollipopBurst: some View {
        ZStack {
            SparkleBurst()
            HStack(spacing: 20) {
                ForEach(0..<reward.lollipops, id: \.self) { i in
                    Text("🍭")
                        .font(.system(size: 104))
                        .rotationEffect(.degrees(revealed ? (i == 0 ? -10 : 10) : -45))
                        .scaleEffect(revealed ? 1 : 0.2)
                        .animation(
                            .spring(response: 0.55, dampingFraction: 0.5).delay(Double(i) * 0.18),
                            value: revealed
                        )
                }
            }
        }
        .frame(height: 150)
    }

    // 무터치 자동 시퀀스: 카운트업 후 사탕 자동 공개 → 총 ~8초 시점에 자동 어트랙트 복귀.
    // 참가자는 일절 터치하지 않는다(요구사항). 운영자 개입은 RootView 숨김 제스처로만.
    private func startAutoSequence() {
        autoTask?.cancel()
        autoTask = Task { @MainActor in
            // 1) 에코포인트 카운트업(~1.5s) 후 사탕 자동 공개
            try? await Task.sleep(nanoseconds: 1_900_000_000)
            if Task.isCancelled { return }
            if reward.lollipops > 0 {
                withAnimation(.spring(response: 0.5, dampingFraction: 0.6)) { revealed = true }
            }
            // 2) 당첨 연출 유지 후 총 ~8초 시점에 자동 복귀(어트랙트 + 감지 재개, §2.1)
            try? await Task.sleep(nanoseconds: 6_100_000_000)
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
                let mag: CGFloat = 130 + CGFloat(i % 4) * 34
                Text(symbols[i % symbols.count])
                    .font(.system(size: 26 + CGFloat(i % 3) * 8))
                    .offset(x: go ? cos(angle) * mag : 0, y: go ? sin(angle) * mag : 0)
                    .opacity(go ? 0 : 1)
                    .scaleEffect(go ? 0.4 : 1)
            }
        }
        .onAppear { withAnimation(.easeOut(duration: 1.1)) { go = true } }
        .allowsHitTesting(false)
    }
}
