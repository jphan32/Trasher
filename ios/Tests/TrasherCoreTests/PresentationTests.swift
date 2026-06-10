// 프레젠테이션 매핑 테스트 — SessionState → ScreenModel.
import XCTest
@testable import TrasherCore

final class PresentationTests: XCTestCase {
    typealias S = SessionCoordinator.SessionState

    func testCategoryDisplayNames() {
        XCTAssertEqual(WasteCategory.pet.displayName, "페트")
        XCTAssertEqual(WasteCategory.can.displayName, "캔")
        XCTAssertEqual(WasteCategory.other.displayName, "기타")
    }

    func testScreenMapping() {
        XCTAssertEqual(screenModel(for: .disconnected).screen, .connecting)
        XCTAssertEqual(screenModel(for: .attract).screen, .attract)
        XCTAssertEqual(screenModel(for: .processing(.sorting)).screen, .processing)
        XCTAssertEqual(screenModel(for: .error(.cameraFail)).screen, .error)
        XCTAssertEqual(screenModel(for: .maintenance).screen, .maintenance)
        XCTAssertEqual(screenModel(for: .stalled).screen, .stalled)
        XCTAssertEqual(screenModel(for: .incompatible(proto: 2)).screen, .error)
    }

    func testRewardCarriesCategory() {
        let m = screenModel(for: .reward(.can))
        XCTAssertEqual(m.screen, .reward)
        XCTAssertEqual(m.category, .can)
        XCTAssertTrue(m.title.contains("캔"))
    }

    func testProcessingTitlesDifferByPiState() {
        XCTAssertNotEqual(
            screenModel(for: .processing(.detecting)).title,
            screenModel(for: .processing(.sorting)).title
        )
        XCTAssertTrue(screenModel(for: .processing(.awaitingResult)).title.contains("분류"))
    }

    func testRoParticleJosa() {
        // 받침 없음/ㄹ → '로', 그 외 → '으로'.
        XCTAssertEqual(WasteCategory.pet.roParticle, "로")    // 페트(트, 받침 없음)
        XCTAssertEqual(WasteCategory.other.roParticle, "로")  // 기타(타, 받침 없음)
        XCTAssertEqual(WasteCategory.can.roParticle, "으로")  // 캔(ㄴ 받침)
        XCTAssertEqual(screenModel(for: .reward(.pet)).title, "페트로 분류했어요")
        XCTAssertEqual(screenModel(for: .reward(.can)).title, "캔으로 분류했어요")
    }
}
