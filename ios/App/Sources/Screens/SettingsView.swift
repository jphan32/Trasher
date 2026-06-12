// 운영자 런타임 설정(튜닝) 화면 — 모터/카메라 타이밍을 Pi에서 불러와 조정·적용. docs/protocol.md §8.
// OperatorView(숨김 진입) 안에서만 열린다. GET /config로 스키마+현재값 로드 → 섹션별 슬라이더 →
// 변경분만 PUT /config. Pi가 clamp한 실제 적용값으로 슬라이더를 보정한다.
import Foundation
import SwiftUI
import TrasherCore

struct SettingsView: View {
    @EnvironmentObject var app: AppModel
    @Environment(\.dismiss) private var dismiss

    private enum Phase: Equatable { case loading, loaded, failed(String) }
    private struct Banner: Equatable { let text: String; let ok: Bool }

    @State private var phase: Phase = .loading
    @State private var fields: [PiConfigField] = []     // 로드된 스키마(min/max/step/label/순서)
    @State private var baseline: [String: Double] = [:]  // 현재 적용값(적용 성공 시 갱신)
    @State private var values: [String: Double] = [:]    // 편집 중 작업 사본
    @State private var saving = false
    @State private var banner: Banner?

    // 변경된(=baseline과 다른) 키만 — PUT은 이 delta만 보낸다.
    private var changed: [String: Double] {
        values.filter { key, value in baseline[key].map { $0 != value } ?? false }
    }

    var body: some View {
        ZStack {
            Color(hex: 0x14140F).ignoresSafeArea()
            VStack(spacing: 0) {
                header
                Divider().overlay(Theme.line)
                content
            }
        }
        .task { await load() }
        .task(id: banner) {
            // 토스트 자동 소멸(3초). banner가 바뀔 때마다 재시작.
            guard banner != nil else { return }
            try? await Task.sleep(nanoseconds: 3_000_000_000)
            banner = nil
        }
    }

    // MARK: 헤더(제목 + 다시 불러오기 + 닫기)
    private var header: some View {
        HStack(alignment: .firstTextBaseline) {
            VStack(alignment: .leading, spacing: 4) {
                Text("설정 · 튜닝").font(Theme.title(36)).foregroundStyle(.white)
                Text("모터·카메라 타이밍 (즉시 적용 · 재시작 불필요)")
                    .font(Theme.caption(18)).foregroundStyle(.white.opacity(0.55))
            }
            Spacer()
            Button { Task { await load() } } label: {
                Image(systemName: "arrow.clockwise").font(.system(size: 22))
                    .foregroundStyle(Theme.sprout)
            }
            .padding(.trailing, 8)
            .disabled(phase == .loading)
            Button("닫기") { dismiss() }
                .font(Theme.body(24)).foregroundStyle(Theme.sprout)
        }
        .padding(.horizontal, 40).padding(.top, 36).padding(.bottom, 20)
    }

    // MARK: 본문(상태별)
    @ViewBuilder private var content: some View {
        switch phase {
        case .loading:
            Spacer()
            ProgressView().tint(Theme.sprout).scaleEffect(1.6)
            Text("불러오는 중…").font(Theme.body(22)).foregroundStyle(.white.opacity(0.6)).padding(.top, 16)
            Spacer()
        case .failed(let message):
            Spacer()
            VStack(spacing: 18) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.system(size: 40)).foregroundStyle(Theme.danger)
                Text(message).font(Theme.body(24)).foregroundStyle(.white)
                    .multilineTextAlignment(.center)
                Button("다시 시도") { Task { await load() } }
                    .font(Theme.body(22)).foregroundStyle(.white)
                    .padding(.horizontal, 28).padding(.vertical, 14)
                    .background(Theme.surfaceHi, in: Capsule())
            }
            .padding(40)
            Spacer()
        case .loaded:
            form
        }
    }

    // MARK: 폼(섹션별 슬라이더) + 하단 적용 바
    private var form: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 30) {
                    ForEach(sections, id: \.self) { section in
                        VStack(alignment: .leading, spacing: 18) {
                            Text(sectionTitle(section))
                                .font(Theme.body(22)).foregroundStyle(Theme.sprout)
                            ForEach(fields.filter { $0.section == section }) { field in
                                row(field)
                            }
                        }
                        .padding(22)
                        .background(.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 18))
                    }
                }
                .padding(.horizontal, 40).padding(.vertical, 24)
            }
            applyBar
        }
    }

    private func row(_ field: PiConfigField) -> some View {
        let value = values[field.key] ?? field.value
        let isChanged = (baseline[field.key]).map { $0 != value } ?? false
        return VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .firstTextBaseline) {
                Text(field.label).font(Theme.body(22)).foregroundStyle(.white)
                if isChanged {
                    Image(systemName: "pencil").font(.system(size: 13)).foregroundStyle(Theme.clay)
                }
                Spacer()
                Text(displayValue(value, field: field))
                    .font(Theme.body(24)).monospacedDigit()
                    .foregroundStyle(isChanged ? Theme.clay : .white)
            }
            Slider(
                value: Binding(
                    get: { values[field.key] ?? field.value },
                    set: { values[field.key] = $0 }
                ),
                in: field.min...field.max, step: field.step
            )
            .tint(Theme.sprout)
            HStack {
                Text(trimNum(field.min)).font(Theme.caption(15)).foregroundStyle(.white.opacity(0.35))
                Spacer()
                Text(trimNum(field.max)).font(Theme.caption(15)).foregroundStyle(.white.opacity(0.35))
            }
        }
    }

    private var applyBar: some View {
        VStack(spacing: 0) {
            if let banner {
                Text(banner.text)
                    .font(Theme.body(20)).foregroundStyle(.white)
                    .frame(maxWidth: .infinity).padding(.vertical, 12)
                    .background(banner.ok ? Theme.sproutDeep : Theme.danger)
            }
            HStack(spacing: 16) {
                Button("되돌리기") { values = baseline }
                    .font(Theme.body(22)).foregroundStyle(.white)
                    .padding(.horizontal, 24).padding(.vertical, 16)
                    .background(.white.opacity(0.08), in: Capsule())
                    .disabled(changed.isEmpty || saving)
                    .opacity(changed.isEmpty || saving ? 0.4 : 1)
                Button { Task { await apply() } } label: {
                    HStack(spacing: 10) {
                        if saving { ProgressView().tint(Theme.onCategory) }
                        Text(changed.isEmpty ? "변경 없음" : "변경 적용 (\(changed.count))")
                            .font(Theme.title(26)).foregroundStyle(Theme.onCategory)
                    }
                    .frame(maxWidth: .infinity).padding(.vertical, 18)
                    .background(Theme.sprout, in: RoundedRectangle(cornerRadius: 18))
                }
                .disabled(changed.isEmpty || saving)
                .opacity(changed.isEmpty || saving ? 0.5 : 1)
            }
            .padding(.horizontal, 40).padding(.vertical, 20)
            .background(Color(hex: 0x101009))
        }
    }

    // MARK: 데이터 로드/적용
    private func load() async {
        phase = .loading
        banner = nil
        do {
            let snapshot = try await app.loadConfig()
            fields = snapshot.fields
            baseline = Dictionary(uniqueKeysWithValues: snapshot.fields.map { ($0.key, $0.value) })
            values = baseline
            phase = .loaded
        } catch {
            phase = .failed(errorText(error))
        }
    }

    private func apply() async {
        let delta = changed
        guard !delta.isEmpty else { return }
        saving = true
        defer { saving = false }
        do {
            let result = try await app.applyConfig(delta)
            // Pi가 clamp한 실제 적용값으로 baseline·values 보정(슬라이더가 진실에 맞춰짐).
            for (key, value) in result.applied {
                baseline[key] = value
                values[key] = value
            }
            // 보낸 키 중 Pi가 echo하지 않은 키(=미반영) — 성공 토스트가 거짓말하지 않게 분리 표기.
            let dropped = Set(delta.keys).subtracting(result.applied.keys)
            if !result.persisted {
                banner = Banner(text: "\(result.applied.count)개 적용 · 저장 실패(재시작 시 초기화)", ok: false)
            } else if !dropped.isEmpty {
                banner = Banner(text: "\(result.applied.count)개 적용 · \(dropped.count)개 미반영", ok: false)
            } else {
                banner = Banner(text: "\(result.applied.count)개 항목 적용됨", ok: true)
            }
        } catch {
            banner = Banner(text: errorText(error), ok: false)
        }
    }

    // MARK: 헬퍼
    private var sections: [String] {
        var seen = Set<String>()
        var order: [String] = []
        for field in fields where !seen.contains(field.section) {
            seen.insert(field.section)
            order.append(field.section)
        }
        return order
    }

    private func sectionTitle(_ section: String) -> String {
        switch section {
        case "belt": return "벨트 (분류 이동)"
        case "servo": return "서보 (게이트·분기)"
        case "vision": return "카메라 · 비전"
        case "timing": return "타이밍"
        case "display": return "상태 표시(OLED)"
        default: return section
        }
    }

    private func displayValue(_ value: Double, field: PiConfigField) -> String {
        let number = trimNum(value, step: field.step)
        return field.unit.isEmpty ? number : "\(number) \(field.unit)"
    }

    /// step 정밀도에 맞춰 소수 자릿수 결정. min/max 힌트엔 step 미지정(기본 정밀도).
    private func trimNum(_ value: Double, step: Double = 0.1) -> String {
        let decimals = step < 0.01 ? 3 : (step < 0.1 ? 2 : 1)
        return String(format: "%.\(decimals)f", value)
    }

    private func errorText(_ error: Error) -> String {
        if let configError = error as? PiConfigError {
            switch configError {
            case .notConnected: return "Pi에 연결되어 있지 않습니다.\n연결 후 다시 시도하세요."
            case .badURL: return "장치 주소 오류"
            case .httpStatus(let code): return "서버 오류 (HTTP \(code))"
            case .malformedResponse: return "응답 형식 오류"
            }
        }
        // 전시 현장 #1 실패: Pi 전원/WiFi 끊김 → URLError. 일반 오류로 묻지 말고 조치 가능한 안내.
        if let urlError = error as? URLError {
            switch urlError.code {
            case .timedOut:
                return "Pi 응답 없음 (시간 초과).\nPi 전원·WiFi를 확인하세요."
            case .cannotConnectToHost, .cannotFindHost,
                 .networkConnectionLost, .notConnectedToInternet:
                return "Pi에 연결할 수 없습니다.\n같은 WiFi인지·Pi 주소를 확인하세요."
            default:
                return "네트워크 오류 (\(urlError.code.rawValue))"
            }
        }
        return "오류: \(error.localizedDescription)"
    }
}
