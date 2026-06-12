// Pi 런타임 튜닝 설정 모델. docs/protocol.md §8(HTTP GET/PUT /config).
//
// Pi가 GET /config로 보내는 자기서술적 스키마(필드별 현재값+min/max/step/label/unit)를 담는다.
// iPad는 이 메타데이터로 폼을 제네릭하게 렌더하므로, Pi가 필드를 추가해도 앱 업데이트가 불필요하다
// (모르는 키는 무시 — Decodable 특성상 추가 키는 자동 무시). BLE 계약과 무관(proto 불변).

import Foundation

/// 튜닝 필드 1개 + 메타데이터. Pi `config_manager.Tunable.to_field`와 1:1 대응(§8.3).
public struct PiConfigField: Decodable, Equatable, Sendable, Identifiable {
    public let key: String       // 안정 식별자(PUT 시 그대로 echo)
    public let section: String   // 그룹(servo/belt/vision/timing/display) — UI 섹션 분류
    public let label: String     // 사람이 읽는 라벨(한국어)
    public let unit: String      // 단위 표기("s" 등, 없으면 "")
    public let type: String      // 값 타입("float")
    public let value: Double      // 현재 적용값
    public let min: Double        // 허용 하한(슬라이더 범위)
    public let max: Double        // 허용 상한
    public let step: Double       // 조정 간격

    public var id: String { key }

    public init(
        key: String, section: String, label: String, unit: String, type: String,
        value: Double, min: Double, max: Double, step: Double
    ) {
        self.key = key; self.section = section; self.label = label; self.unit = unit
        self.type = type; self.value = value; self.min = min; self.max = max; self.step = step
    }
}

/// `GET /config` 응답 전체. `fw`=펌웨어 버전(표시용, 없을 수 있음), `fields`=튜닝 필드 목록.
public struct PiConfigSnapshot: Decodable, Equatable, Sendable {
    public let fw: String?
    public let fields: [PiConfigField]

    public init(fw: String?, fields: [PiConfigField]) {
        self.fw = fw
        self.fields = fields
    }
}
