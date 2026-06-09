// SessionState → 화면 표현 매핑(프레젠테이션 로직). 호스트 테스트 가능.
// SwiftUI 뷰는 이 ScreenModel만 렌더링한다 → UI 상태머신을 뷰와 분리해 검증.

import Foundation

public extension WasteCategory {
    /// 참여자 표시용 한글명.
    var displayName: String {
        switch self {
        case .pet: return "페트"
        case .can: return "캔"
        case .other: return "기타"
        }
    }
}

public enum Screen: String, Equatable, Sendable {
    case connecting   // 미연결/연결중
    case attract      // 투입 대기(어트랙트)
    case processing   // 감지~분류~이동 진행
    case reward       // 결과 + 에코포인트/막대사탕 보상
    case error        // Pi 오류
    case maintenance  // 점검 모드
    case stalled      // 응답 없음
}

public struct ScreenModel: Equatable, Sendable {
    public let screen: Screen
    public let title: String
    public let subtitle: String
    public let category: WasteCategory?  // reward일 때만

    public init(screen: Screen, title: String, subtitle: String, category: WasteCategory? = nil) {
        self.screen = screen
        self.title = title
        self.subtitle = subtitle
        self.category = category
    }
}

/// SessionCoordinator.SessionState → ScreenModel. 한글 카피 포함.
public func screenModel(for state: SessionCoordinator.SessionState) -> ScreenModel {
    switch state {
    case .disconnected:
        return ScreenModel(screen: .connecting, title: "연결 중", subtitle: "분류기를 찾고 있어요")
    case .incompatible(let proto):
        return ScreenModel(screen: .error, title: "버전 불일치",
                           subtitle: "분류기 프로토콜 v\(proto) — 앱 업데이트가 필요해요")
    case .attract:
        return ScreenModel(screen: .attract, title: "쓰레기를 넣어주세요",
                           subtitle: "AI가 종류를 알아맞혀요")
    case .processing(let piState):
        return ScreenModel(screen: .processing, title: processingTitle(piState),
                           subtitle: "잠시만 기다려주세요")
    case .reward(let category):
        return ScreenModel(screen: .reward, title: "\(category.displayName)으로 분류했어요",
                           subtitle: "탄소를 줄였어요! 보상을 받아 가세요", category: category)
    case .error(let code):
        return ScreenModel(screen: .error, title: "잠시 문제가 생겼어요",
                           subtitle: "관리자를 호출해주세요 (\(code.rawValue))")
    case .maintenance:
        return ScreenModel(screen: .maintenance, title: "점검 중", subtitle: "잠시 후 다시 이용해주세요")
    case .stalled:
        return ScreenModel(screen: .stalled, title: "분류기 응답 없음", subtitle: "연결을 확인하고 있어요")
    }
}

private func processingTitle(_ piState: PiState) -> String {
    switch piState {
    case .detecting, .capturing: return "쓰레기를 인식하고 있어요"
    case .awaitingResult: return "AI가 분류하고 있어요"
    case .sorting: return "분류함으로 옮기고 있어요"
    default: return "처리 중"
    }
}
