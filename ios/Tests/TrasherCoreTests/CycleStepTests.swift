// 사이클 단계 매핑 테스트.
import XCTest
@testable import TrasherCore

final class CycleStepTests: XCTestCase {
    typealias S = SessionCoordinator.SessionState

    func testFourStepsInOrder() {
        XCTAssertEqual(CycleStep.allCases, [.capture, .recognize, .move, .sort])
        XCTAssertEqual(CycleStep.allCases.map(\.label), ["촬영", "AI 인식", "이동", "분류"])
    }

    func testStateMapping() {
        XCTAssertEqual(cycleStep(for: .processing(.detecting)), .capture)
        XCTAssertEqual(cycleStep(for: .processing(.capturing)), .capture)
        XCTAssertEqual(cycleStep(for: .processing(.awaitingResult)), .recognize)
        XCTAssertEqual(cycleStep(for: .processing(.sorting)), .move)
        XCTAssertEqual(cycleStep(for: .reward(.pet)), .sort)
    }

    func testNoStepOutsideCycle() {
        XCTAssertNil(cycleStep(for: .attract))
        XCTAssertNil(cycleStep(for: .disconnected))
        XCTAssertNil(cycleStep(for: .error(.cameraFail)))
        XCTAssertNil(cycleStep(for: .stalled))
    }

    func testRawValueProgression() {
        // 단계가 진행할수록 rawValue가 증가(스테퍼 완료/현재/대기 판정용).
        XCTAssertLessThan(CycleStep.capture.rawValue, CycleStep.recognize.rawValue)
        XCTAssertLessThan(CycleStep.move.rawValue, CycleStep.sort.rawValue)
    }
}
