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

## iOS 앱 (Xcode)

앱 타깃은 [XcodeGen](https://github.com/yonaskolb/XcodeGen)으로 생성한다(`project.yml`이 진실, `.xcodeproj`는 gitignore).

```bash
cd ios/App
xcodegen generate                 # project.yml → Trasher.xcodeproj
# 시뮬레이터 빌드(검증)
xcodebuild -project Trasher.xcodeproj -scheme Trasher \
  -destination 'generic/platform=iOS Simulator' build
# 또는 Xcode로 Trasher.xcodeproj 열어 실기기 실행(BLE는 실기기 필수)
```

화면: 어트랙트→진행→결과(+씨앗 추첨)→오류/정지/점검. 좌상단 3초 길게 눌러 운영자 정비 화면.
디자인: 유기적 에디토리얼-식물 컨셉(크림 페이퍼/딥 포레스트/새싹·클레이), 카테고리 색 구분.

## 전시 무인운영(키오스크) 메모

- 앱이 화면 자동 잠금을 끈다(`isIdleTimerDisabled`). 포그라운드 복귀 시 BLE 재스캔.
- BLE 자동 재연결: 연결 끊김·연결 실패 시 자동 재스캔(BLECentral).
- **Guided Access**(설정 → 손쉬운 사용 → 가이드 접근)를 켜 앱 이탈을 막을 것(코드로 강제 불가).
- 전원/네트워크는 부스 운영 체크리스트로 관리(라우터 인터넷, AP격리 OFF — docs/protocol.md).
