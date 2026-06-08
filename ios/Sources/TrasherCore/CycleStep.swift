// 처리 사이클 단계: 촬영 → AI 인식 → 이동 → 분류. 진행 스테퍼 UI 구동(호스트 테스트 가능).

import Foundation

public enum CycleStep: Int, CaseIterable, Sendable, Equatable {
    case capture     // 촬영
    case recognize   // AI 인식
    case move        // 이동
    case sort        // 분류

    public var label: String {
        switch self {
        case .capture: return "촬영"
        case .recognize: return "AI 인식"
        case .move: return "이동"
        case .sort: return "분류"
        }
    }

    /// SF Symbol 이름(뷰에서 사용).
    public var symbol: String {
        switch self {
        case .capture: return "camera.fill"
        case .recognize: return "sparkles"
        case .move: return "arrow.left.arrow.right"
        case .sort: return "tray.full.fill"
        }
    }
}

/// 세션 상태 → 현재 단계. processing/reward에서만 단계가 있고, 그 외(어트랙트/오류 등)는 nil.
public func cycleStep(for state: SessionCoordinator.SessionState) -> CycleStep? {
    switch state {
    case .processing(let piState):
        switch piState {
        case .detecting, .capturing: return .capture
        case .awaitingResult: return .recognize
        case .sorting: return .move
        default: return .capture
        }
    case .reward:
        return .sort
    default:
        return nil
    }
}
