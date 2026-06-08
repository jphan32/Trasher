// swift-tools-version:6.0
import PackageDescription

// TrasherCore: iPad 앱의 순수 로직 코어 (프로토콜 미러 + 분류 추상화 + 정규화).
// CoreBluetooth/SwiftUI에 비의존 → 호스트(macOS)에서 `swift test`로 검증 가능.
// 계약: ../docs/protocol.md. Pi의 pi/src/trash_sorter/protocol.py와 수동 동기화.
let package = Package(
    name: "TrasherCore",
    platforms: [.iOS(.v16), .macOS(.v13)],
    products: [
        .library(name: "TrasherCore", targets: ["TrasherCore"])
    ],
    targets: [
        .target(name: "TrasherCore"),
        .testTarget(name: "TrasherCoreTests", dependencies: ["TrasherCore"]),
    ]
)
