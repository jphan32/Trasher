# iPad 앱 (Trasher)

AI 쓰레기 자동 분류기의 iPad 측. SwiftUI + CoreBluetooth(Central) + URLSession.
계약 문서: [`../docs/protocol.md`](../docs/protocol.md).

## 구조 (2계층)

- **`TrasherCore`** (SwiftPM 라이브러리) — 순수 로직 코어. CoreBluetooth/SwiftUI 비의존이라
  **호스트(macOS)에서 `swift test`로 검증**한다. Pi의 `pi/` mock 테스트와 같은 철학.
  - `Protocol.swift` — GATT UUID·enum·Codable 메시지 (docs/protocol.md 미러, Pi `protocol.py`와 동기)
  - `Classification.swift` — `ClassificationService` 추상화 + `MockClassificationService` + `CategoryNormalizer`(라벨→3분류 + 임계값, §4.4)
- **Xcode 앱 타깃** (예정) — `TrasherCore`를 소비하는 iOS 앱: CoreBluetooth Central, 사진 HTTP 다운로드,
  SwiftUI 화면(어트랙트→감지→분류→결과→씨앗), 운영자 정비 화면.

## 코어 개발/테스트 (macOS)

```bash
cd ios
swift build
swift test      # 프로토콜 라운드트립 + 정규화 검증 (호스트)
```

## 원칙

- 외부 분류 API 미정 → `ClassificationService` 뒤에서 개발. 실제 API 확정 시 `RemoteClassificationService`만 교체.
- API 라벨 → 3분류("페트/캔/기타") 정규화 + confidence 임계값은 **iPad 책임**. Pi에는 항상 3분류만 전달.
- 실 BLE 검증은 시뮬레이터가 아닌 **실기기(iPad)** 에서만 가능.
