// 화면들 — 어트랙트 / 진행 / 상태(연결·오류·정지·점검).
import SwiftUI
import TrasherCore

// MARK: 어트랙트(투입 대기)
struct AttractView: View {
    let model: ScreenModel
    @EnvironmentObject var app: AppModel
    @State private var breathe = false

    var body: some View {
        VStack(spacing: 40) {
            Spacer()
            Text("♻️")
                .font(.system(size: 140))
                .scaleEffect(breathe ? 1.06 : 0.94)
                .animation(.easeInOut(duration: 1.8).repeatForever(autoreverses: true), value: breathe)
            Text(model.title)
                .font(Theme.display(104))
                .foregroundStyle(Theme.ink)
                .multilineTextAlignment(.center)
                .lineSpacing(10)
            Text(model.subtitle)
                .font(Theme.body(34))
                .foregroundStyle(Theme.inkSoft)
            if app.stats.total > 0 {
                Text("지금까지 ♻️ \(app.stats.total)개 분류했어요")
                    .font(Theme.caption(24))
                    .foregroundStyle(Theme.sprout)
                    .padding(.top, 8)
            }
            Spacer()
            Image(systemName: "arrow.down")
                .font(.system(size: 72, weight: .black))
                .foregroundStyle(Theme.sprout)
                .offset(y: breathe ? 12 : -12)
                .animation(.easeInOut(duration: 1.2).repeatForever(autoreverses: true), value: breathe)
                .padding(.bottom, 60)
        }
        .onAppear { breathe = true }
    }
}

// MARK: 진행(인식→분류→이동)
struct ProcessingView: View {
    let model: ScreenModel
    @EnvironmentObject var app: AppModel
    @State private var float = false

    var body: some View {
        VStack(spacing: 28) {
            StepperView(current: app.step ?? .capture)
                .padding(.top, 28).padding(.horizontal, 44)
            Spacer()
            // 현재 처리중인 쓰레기 사진 카드(폴라로이드 느낌)
            ZStack {
                RoundedRectangle(cornerRadius: 28).fill(.white)
                    .overlay(RoundedRectangle(cornerRadius: 28).stroke(Theme.paperDeep, lineWidth: 4))
                    .shadow(color: Theme.ink.opacity(0.12), radius: 18, y: 10)
                if let photo = app.photo {
                    Image(uiImage: photo).resizable().scaledToFill()
                        .clipShape(RoundedRectangle(cornerRadius: 22)).padding(12)
                } else {
                    Image(systemName: "camera.viewfinder")
                        .font(.system(size: 96)).foregroundStyle(Theme.sprout.opacity(0.6))
                }
            }
            .frame(width: 300, height: 300)
            .offset(y: float ? -8 : 8)
            .animation(.easeInOut(duration: 1.8).repeatForever(autoreverses: true), value: float)

            Text(model.title).font(Theme.title(46)).foregroundStyle(Theme.ink)
                .multilineTextAlignment(.center).lineSpacing(6)
            // AI 설명(재활용 팁) — 인식 후 사진과 함께 표시
            if let tip = app.tip, !tip.isEmpty {
                TipBox(text: tip).padding(.horizontal, 32)
            }
            Spacer()
        }
        .onAppear { float = true }
    }
}

// MARK: 상태(연결·오류·정지·점검) 공통
struct StatusView: View {
    let model: ScreenModel
    let accent: Color
    let symbol: String

    var body: some View {
        VStack(spacing: 32) {
            Spacer()
            Image(systemName: symbol).font(.system(size: 110)).foregroundStyle(accent)
            Text(model.title).font(Theme.title(54)).foregroundStyle(Theme.ink)
                .multilineTextAlignment(.center).lineSpacing(6)
            Text(model.subtitle).font(Theme.body(26)).foregroundStyle(Theme.inkSoft)
                .multilineTextAlignment(.center).lineSpacing(4)
            Spacer()
        }
        .padding(48)
    }
}
