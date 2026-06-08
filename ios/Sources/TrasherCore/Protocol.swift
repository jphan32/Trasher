// BLE GATT 프로토콜 + 분류 데이터 모델 (Swift 미러).
//
// 단일 진실 공급원은 ../../docs/protocol.md. 이 파일은 §1, §3, §4를 Swift로 **수동 동기화**한 것.
// Pi 측 미러는 pi/src/trash_sorter/protocol.py. 문서를 바꾸면 양쪽을 함께 갱신한다.
//
// null 생략 규약(§3): nil optional은 키를 생략한다. Swift Codable 합성 인코딩이
// encodeIfPresent/decodeIfPresent를 쓰므로 nil→키 부재, 키 부재→nil 으로 자동 일치한다.

import Foundation

public enum Proto {
    public static let version = 1

    // §1 GATT UUID
    public static let serviceUUID = "4F520100-7A69-4B43-8E2D-1C9A7F3B0001"
    public static let charDeviceInfo = "4F520101-7A69-4B43-8E2D-1C9A7F3B0001"
    public static let charStatus = "4F520102-7A69-4B43-8E2D-1C9A7F3B0001"
    public static let charPhotoReady = "4F520103-7A69-4B43-8E2D-1C9A7F3B0001"
    public static let charClassificationResult = "4F520104-7A69-4B43-8E2D-1C9A7F3B0001"
    public static let charCommand = "4F520105-7A69-4B43-8E2D-1C9A7F3B0001"
    public static let charCommandAck = "4F520106-7A69-4B43-8E2D-1C9A7F3B0001"

    public static let localName = "sorter-01"
}

// §4.1 3분류 enum
public enum WasteCategory: String, Codable, Sendable, CaseIterable {
    case pet    // 페트
    case can    // 캔
    case other  // 기타 (안전 기본값)
}

// §2 상태 머신 상태
public enum PiState: String, Codable, Sendable {
    case idle, detecting, capturing
    case awaitingResult = "awaiting_result"
    case sorting, error, maintenance
}

// §3.5 명령
public enum CommandType: String, Codable, Sendable {
    case start, stop, reset, sort, belt, calibrate, maintenance, estop
}

// §5 에러 코드
public enum ErrorCode: String, Codable, Sendable {
    case cameraFail = "camera_fail"
    case motorFail = "motor_fail"
    case beltJam = "belt_jam"
    case resultTimeout = "result_timeout"
    case estopped
    case `internal`
}

// §3.1 DeviceInfo (Read)
public struct DeviceInfo: Codable, Equatable, Sendable {
    public let fw: String
    public let proto: Int
    public let ip: String
    public let port: Int
    public let name: String
    public init(fw: String, ip: String, port: Int, name: String = Proto.localName, proto: Int = Proto.version) {
        self.fw = fw; self.ip = ip; self.port = port; self.name = name; self.proto = proto
    }
}

// §3.2 Status (Notify, Read)
public struct Status: Codable, Equatable, Sendable {
    public let state: PiState
    public let cycle: Int
    public let seq: Int
    public let err: ErrorCode?
    public let lastSort: WasteCategory?
    public init(state: PiState, cycle: Int, seq: Int, err: ErrorCode? = nil, lastSort: WasteCategory? = nil) {
        self.state = state; self.cycle = cycle; self.seq = seq; self.err = err; self.lastSort = lastSort
    }
}

// §3.3 PhotoReady (Notify)
public struct PhotoReady: Codable, Equatable, Sendable {
    public let cycle: Int
    public let path: String
    public let w: Int?
    public let h: Int?
    public let ts: Int?
    public init(cycle: Int, path: String, w: Int? = nil, h: Int? = nil, ts: Int? = nil) {
        self.cycle = cycle; self.path = path; self.w = w; self.h = h; self.ts = ts
    }
}

// §3.4 ClassificationResult (Write w/ response). iPad → Pi
public struct ClassificationResult: Codable, Equatable, Sendable {
    public let cycle: Int
    public let category: WasteCategory
    public let confidence: Double
    public let raw: String?
    public init(cycle: Int, category: WasteCategory, confidence: Double, raw: String? = nil) {
        self.cycle = cycle; self.category = category; self.confidence = confidence; self.raw = raw
    }
}

// §3.5 Command (Write w/ response). iPad → Pi
public struct Command: Codable, Equatable, Sendable {
    public let cmd: CommandType
    public let arg: String?
    public let id: Int
    public init(cmd: CommandType, id: Int, arg: String? = nil) {
        self.cmd = cmd; self.id = id; self.arg = arg
    }
}

// §3.6 CommandAck (Notify). Pi → iPad
public struct CommandAck: Codable, Equatable, Sendable {
    public let id: Int
    public let ok: Bool
    public let err: ErrorCode?
    public init(id: Int, ok: Bool, err: ErrorCode? = nil) {
        self.id = id; self.ok = ok; self.err = err
    }
}

// JSON 직렬화 헬퍼 — 모든 특성 페이로드는 UTF-8 JSON.
public enum Wire {
    public static func encode<T: Encodable>(_ value: T) throws -> Data {
        try JSONEncoder().encode(value)
    }
    public static func decode<T: Decodable>(_ type: T.Type, from data: Data) throws -> T {
        try JSONDecoder().decode(type, from: data)
    }
}
