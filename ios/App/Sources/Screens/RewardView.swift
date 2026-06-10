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

            HStack(alignment: .center, spacing: 28) {
                leftColumn
                ecoCard
            }
            .padding(.horizontal, 24)

            Spacer(minLength: 0)

            // 리셋 임박 힌트 — 고정 슬롯(항상 자리 차지, 불투명도만 토글)으로 레이아웃 흔들림/클리핑 방지.
            Text("곧 처음 화면으로 돌아가요")
                .font(Theme.caption(20)).foregroundStyle(Theme.inkSoft)
                .opacity(showResetHint ? 1 : 0)
                .padding(.bottom, 10)
                .animation(.easeIn(duration: 0.3), value: showResetHint)
        }
        .padding(.vertical, 22)
        .onAppear {
            // 재사용 대비 상태 초기화(뷰가 .reward로 재진입해도 깨끗이 시작).
            revealed = false; showResetHint = false; displayedPoints = 0
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
                    .lineLimit(1).minimumScaleFactor(0.6)
                    .padding(.horizontal, 30).padding(.vertical, 12)
                    .background(Theme.category(category), in: RoundedRectangle(cornerRadius: 22))
                    .scaleEffect(stamp ? 1 : 0.6)
                    .rotationEffect(.degrees(stamp ? 0 : -8))
                    .animation(.spring(response: 0.5, dampingFraction: 0.55), value: stamp)
                Text("\(category.roParticle)\n분류했어요").font(Theme.body(24)).foregroundStyle(Theme.inkSoft)
            }
            if let tip = app.tip, !tip.isEmpty {
                TipBox(text: tip)
            }
        }
        .frame(maxWidth: 400, alignment: .leading)
    }

    // MARK: 우측 — 에코포인트 링 + 탄소절감 + 보상 리빌
    private var ecoCard: some View {
        VStack(spacing: 16) {
            // 씨앗 도감(시그니처) — 에코포인트만큼 자라는 식물. 보상은 가지에 열리는 열매.
            SeedlingView(category: category, growth: Double(reward.ecoPoints) / 100,
                         fruits: reward.lollipops, showFruits: revealed)
                .frame(width: 200, height: 200)
            VStack(spacing: 0) {
                Text("🌍 \(displayedPoints)").font(Theme.display(46)).foregroundStyle(Theme.ink)
                Text("에코포인트").font(Theme.caption(16)).foregroundStyle(Theme.inkSoft)
            }

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
        .frame(maxWidth: 440)
        .background(.white.opacity(0.5), in: RoundedRectangle(cornerRadius: 32))
    }

    // 카피는 lollipops가 아니라 recyclable로 분기(재활용 가능하나 0점인 경우 오표기 방지, trash-iwg).
    private var ecoHeadline: String {
        if reward.lollipops > 0 { return "탄소절감에 기여했어요! 막대사탕을 받아 가세요" }
        if reward.recyclable { return "재활용 가능한 자원이에요! 분리배출 고마워요" }
        return "재활용이 어려운 쓰레기예요"
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
            VStack(spacing: 10) {
                Text(reward.recyclable ? "♻️" : "🗑️").font(.system(size: 48))
                Text(reward.recyclable
                     ? "분리배출 해주셔서 고마워요!"
                     : "재활용 가능한 쓰레기를 넣으면\n막대사탕을 받을 수 있어요")
                    .font(Theme.body(20)).foregroundStyle(Theme.inkSoft)
                    .multilineTextAlignment(.center)
            }
            .frame(height: 86)
            .transition(.opacity)
        } else {
            // 당첨 — 막대사탕은 식물 가지에 열매로 열림(SeedlingView). 여기선 축하 텍스트+스파클.
            // 고정 높이 슬롯으로 공개 전후 레이아웃 흔들림 방지.
            ZStack {
                if revealed { SparkleBurst() }
                Text(revealed ? "막대사탕 \(reward.lollipops)개 당첨!" : " ")
                    .font(Theme.title(34)).foregroundStyle(Theme.clay)
                    .scaleEffect(revealed ? 1 : 0.6)
                    .animation(.spring(response: 0.5, dampingFraction: 0.6), value: revealed)
            }
            .frame(height: 86)
        }
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
            // 3) 리셋 임박 힌트(사진 촬영 보호) 후 복귀 — 애니메이션은 뷰의 .animation이 담당
            showResetHint = true
            try? await Task.sleep(nanoseconds: 2_000_000_000)
            if Task.isCancelled { return }
            app.finishReward()
        }
    }

    // 에코포인트 카운트업 애니메이션(0 → 목표).
    private func startCountUp(to target: Int) {
        countTask?.cancel()   // 기존 카운트 취소를 guard보다 먼저(잔여 task가 값 덮어쓰지 않게)
        guard target > 0 else { displayedPoints = 0; return }
        countTask = Task { @MainActor in
            let steps = min(target, 35)
            for i in 0...steps {
                if Task.isCancelled { return }
                displayedPoints = Int((Double(target) * Double(i) / Double(steps)).rounded())
                try? await Task.sleep(nanoseconds: 28_000_000)
            }
            if Task.isCancelled { return }
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
                let mag: CGFloat = 52 + CGFloat(i % 4) * 12   // 86pt 슬롯 내로 반경 축소(겹침 방지)
                Text(symbols[i % symbols.count])
                    .font(.system(size: 20 + CGFloat(i % 3) * 5))
                    .offset(x: go ? cos(angle) * mag : 0, y: go ? sin(angle) * mag : 0)
                    .opacity(go ? 0 : 1)
                    .scaleEffect(go ? 0.4 : 1)
            }
        }
        .onAppear { withAnimation(.easeOut(duration: 1.1)) { go = true } }
        .allowsHitTesting(false)
    }
}
