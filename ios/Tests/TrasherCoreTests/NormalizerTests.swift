// 라벨→3분류 정규화 + 임계값 + 폴백 테스트. docs/protocol.md §4.4, §6.
import XCTest
@testable import TrasherCore

final class NormalizerTests: XCTestCase {
    let norm = CategoryNormalizer(threshold: 0.5)

    func testMapsKnownLabels() {
        XCTAssertEqual(norm.normalize(.init(label: "PET_bottle", confidence: 0.9), cycle: 1).category, .pet)
        XCTAssertEqual(norm.normalize(.init(label: "aluminum_can", confidence: 0.9), cycle: 1).category, .can)
        XCTAssertEqual(norm.normalize(.init(label: "페트", confidence: 0.9), cycle: 1).category, .pet)
    }

    func testUnknownLabelFallsBackToOther() {
        XCTAssertEqual(norm.normalize(.init(label: "banana", confidence: 0.9), cycle: 1).category, .other)
    }

    func testLowConfidenceForcesOther() {
        // 라벨은 pet이지만 임계값 미만 → 안전 기본값 other.
        XCTAssertEqual(norm.normalize(.init(label: "pet", confidence: 0.3), cycle: 1).category, .other)
    }

    func testNormalizePreservesCycleAndRaw() {
        let r = norm.normalize(.init(label: "can", confidence: 0.8), cycle: 42)
        XCTAssertEqual(r.cycle, 42)
        XCTAssertEqual(r.raw, "can")
        XCTAssertEqual(r.confidence, 0.8, accuracy: 1e-9)
    }

    func testFallbackIsOther() {
        let f = norm.fallback(cycle: 7, reason: "timeout")
        XCTAssertEqual(f.category, .other)
        XCTAssertEqual(f.cycle, 7)
        XCTAssertEqual(f.confidence, 0)
        XCTAssertEqual(f.raw, "timeout")
    }

    func testMockServiceProducesConfiguredResult() async throws {
        let svc = MockClassificationService(label: "can", confidence: 0.88)
        let raw = try await svc.classify(imageURL: URL(string: "http://x/1.jpg")!)
        XCTAssertEqual(norm.normalize(raw, cycle: 3).category, .can)
    }
}
