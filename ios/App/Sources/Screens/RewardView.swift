// 결과 + 씨앗 추첨 화면. 카테고리 색 배지 → 씨앗 5종 중 1개 랜덤 추첨 인터랙션.
import SwiftUI
import TrasherCore

struct RewardView: View {
    let model: ScreenModel
    @EnvironmentObject var app: AppModel
    @State private var stamp = false

    private var category: WasteCategory { model.category ?? .other }

    var body: some View {
        VStack(spacing: 36) {
            // 투입된 쓰레기 사진(있으면)
            if let photo = app.photo {
                Image(uiImage: photo).resizable().scaledToFill()
                    .frame(width: 160, height: 160).clipShape(RoundedRectangle(cornerRadius: 24))
                    .overlay(RoundedRectangle(cornerRadius: 24).stroke(Theme.paperDeep, lineWidth: 3))
            }
            // 카테고리 배지
            VStack(spacing: 12) {
                Text(category.displayName)
                    .font(Theme.display(120))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 64).padding(.vertical, 28)
                    .background(Theme.category(category), in: RoundedRectangle(cornerRadius: 40))
                    .scaleEffect(stamp ? 1 : 0.6)
                    .rotationEffect(.degrees(stamp ? 0 : -8))
                    .animation(.spring(response: 0.5, dampingFraction: 0.55), value: stamp)
                Text("으로 분류했어요").font(Theme.body(30)).foregroundStyle(Theme.inkSoft)
            }
            .padding(.top, 24)

            // 재활용 팁(부가정보) — Gemini가 제공
            if let tip = app.tip, !tip.isEmpty {
                HStack(alignment: .top, spacing: 12) {
                    Text("💡").font(.system(size: 30))
                    Text(tip)
                        .font(Theme.body(24))
                        .foregroundStyle(Theme.ink)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(20)
                .frame(maxWidth: 640)
                .background(Theme.sprout.opacity(0.14), in: RoundedRectangle(cornerRadius: 20))
                .padding(.horizontal, 32)
            }

            Divider().frame(width: 320).overlay(Theme.paperDeep)

            // 씨앗 추첨
            if let seed = app.drawnSeed {
                VStack(spacing: 20) {
                    Text("🌱").font(.system(size: 120)).transition(.scale.combined(with: .opacity))
                    Text(seed.name).font(Theme.title(64)).foregroundStyle(Theme.ink)
                    Text("씨앗을 받아 가세요!").font(Theme.body(28)).foregroundStyle(Theme.sprout)
                    Button(action: { app.finishSeed() }) {
                        Text("다 받았어요")
                            .font(Theme.body(30)).foregroundStyle(.white)
                            .padding(.horizontal, 56).padding(.vertical, 22)
                            .background(Theme.ink, in: Capsule())
                    }
                    .padding(.top, 8)
                }
                .transition(.scale(scale: 0.8).combined(with: .opacity))
            } else {
                VStack(spacing: 24) {
                    Text("선물 씨앗을 뽑아보세요").font(Theme.body(30)).foregroundStyle(Theme.inkSoft)
                    HStack(spacing: 18) {
                        ForEach(app.seeds) { _ in
                            RoundedRectangle(cornerRadius: 16)
                                .fill(Theme.sprout.opacity(0.18))
                                .overlay(Text("🌰").font(.system(size: 40)))
                                .frame(width: 88, height: 110)
                        }
                    }
                    Button(action: { withAnimation { app.drawSeed() } }) {
                        Text("씨앗 뽑기 🎁")
                            .font(Theme.title(40)).foregroundStyle(.white)
                            .padding(.horizontal, 64).padding(.vertical, 26)
                            .background(Theme.clay, in: Capsule())
                    }
                }
            }
            Spacer()
        }
        .padding(40)
        .onAppear { stamp = true }
    }
}
