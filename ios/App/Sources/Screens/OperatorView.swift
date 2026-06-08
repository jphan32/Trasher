// 운영자(정비) 화면 — 숨김 제스처(좌상단 3초)로 진입. 수동 제어 + 상태.
import SwiftUI
import TrasherCore

struct OperatorView: View {
    @EnvironmentObject var app: AppModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            Color(hex: 0x14140F).ignoresSafeArea()
            VStack(alignment: .leading, spacing: 28) {
                HStack {
                    Text("운영자 정비").font(Theme.title(40)).foregroundStyle(.white)
                    Spacer()
                    Button("닫기") { dismiss() }
                        .font(Theme.body(24)).foregroundStyle(Theme.sprout)
                }

                Text("현재: \(app.model.title)").font(Theme.body(24)).foregroundStyle(.white.opacity(0.7))

                grid
                Spacer()
                Button(role: .destructive, action: { app.operatorCommand(.estop) }) {
                    Text("비상 정지 (E-STOP)")
                        .font(Theme.title(34)).foregroundStyle(.white)
                        .frame(maxWidth: .infinity).padding(.vertical, 26)
                        .background(Theme.clay, in: RoundedRectangle(cornerRadius: 20))
                }
            }
            .padding(48)
        }
    }

    private var grid: some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 18) {
            opButton("감지 시작", "play.fill") { app.operatorCommand(.start) }
            opButton("감지 정지", "pause.fill") { app.operatorCommand(.stop) }
            opButton("리셋", "arrow.counterclockwise") { app.operatorCommand(.reset) }
            opButton("벨트 구동", "forward.fill") { app.operatorCommand(.belt, arg: "fwd") }
            opButton("벨트 정지", "stop.fill") { app.operatorCommand(.belt, arg: "stop") }
            opButton("캘리브레이션", "scope") { app.operatorCommand(.calibrate) }
            opButton("페트로 분류", "drop.fill") { app.operatorCommand(.sort, arg: "pet") }
            opButton("캔으로 분류", "cylinder.fill") { app.operatorCommand(.sort, arg: "can") }
            opButton("기타로 분류", "questionmark") { app.operatorCommand(.sort, arg: "other") }
        }
    }

    private func opButton(_ title: String, _ symbol: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 10) {
                Image(systemName: symbol).font(.system(size: 30))
                Text(title).font(Theme.caption(20))
            }
            .foregroundStyle(.white)
            .frame(maxWidth: .infinity).padding(.vertical, 22)
            .background(.white.opacity(0.08), in: RoundedRectangle(cornerRadius: 16))
        }
    }
}
