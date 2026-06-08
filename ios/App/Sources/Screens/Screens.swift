// 화면들 — 어트랙트 / 진행 / 상태(연결·오류·정지·점검).
import SwiftUI
import TrasherCore

// MARK: 어트랙트(투입 대기)
struct AttractView: View {
    let model: ScreenModel
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
            Text(model.subtitle)
                .font(Theme.body(34))
                .foregroundStyle(Theme.inkSoft)
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
    @State private var spin = false

    var body: some View {
        VStack(spacing: 48) {
            Spacer()
            ZStack {
                Circle().stroke(Theme.paperDeep, lineWidth: 14).frame(width: 220, height: 220)
                Circle().trim(from: 0, to: 0.28)
                    .stroke(Theme.sprout, style: StrokeStyle(lineWidth: 14, lineCap: .round))
                    .frame(width: 220, height: 220)
                    .rotationEffect(.degrees(spin ? 360 : 0))
                    .animation(.linear(duration: 1).repeatForever(autoreverses: false), value: spin)
                // 투입된 쓰레기 사진(있으면 원형 마스크로 표시), 없으면 새싹 아이콘
                if let photo = app.photo {
                    Image(uiImage: photo).resizable().scaledToFill()
                        .frame(width: 180, height: 180).clipShape(Circle())
                } else {
                    Image(systemName: "leaf.fill").font(.system(size: 72)).foregroundStyle(Theme.sprout)
                }
            }
            Text(model.title).font(Theme.title(56)).foregroundStyle(Theme.ink)
                .multilineTextAlignment(.center)
            Text(model.subtitle).font(Theme.body(28)).foregroundStyle(Theme.inkSoft)
            Spacer()
        }
        .onAppear { spin = true }
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
                .multilineTextAlignment(.center)
            Text(model.subtitle).font(Theme.body(26)).foregroundStyle(Theme.inkSoft)
                .multilineTextAlignment(.center)
            Spacer()
        }
        .padding(48)
    }
}
