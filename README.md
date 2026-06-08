# AI 쓰레기 자동 분류기 (Trasher)

순환자원 홍보용 전시/체험 부스 프로토타입. 참여자가 쓰레기를 투입하면 AI가 종류를 판별하고,
컨베이어 벨트가 자동으로 분류한 뒤, 보상으로 씨앗을 제공하는 인터랙티브 데모.

## 구성 (모노레포)

```
/ios       iPad 앱 — Swift / SwiftUI / CoreBluetooth(Central)   (사용자 대면 컨트롤러·시각화)
/pi        Raspberry Pi 제어 프로그램 — Python                  (비전·서보·벨트 + 사진/분류 HTTP)
/docs      프로토콜·설계 문서 (단일 진실 공급원)
/fixtures  교차언어 계약 골든 픽스처
```

## 동작 (1회 분류 사이클)

```
[Pi]   카메라 변이 감지 → 촬영 → BLE notification "사진 준비됨"
[iPad] 사진 HTTP GET(표시용) → POST Pi:/classify/{cycle} → {3분류 + 재활용 팁} → 3분류 BLE 전송
[Pi]   결과 수신 → 서보로 경로 설정 → 벨트 구동 → 분리수거함 이동
[iPad] 결과 시각화(+ 재활용 팁) → 씨앗 5종 랜덤 추첨 → 참여자에게 제공
```

분류는 **Gemini 3.5 Flash**(structured output)가 수행하며, **Pi의 `/classify/{cycle}` 엔드포인트**에 통합돼 있다.
iPad는 이미지 대신 cycle ID만 보내고(재업로드 없음) Pi가 로컬 사진을 읽어 Gemini를 호출한다.
**호출자/결과 핸들러는 iPad**(UI + BLE 주도), 키는 Pi가 보유(`secret/`, gitignore).

두 통신 채널: **제어·상태·결과 = BLE**(상시 연결), **사진 = 로컬 WiFi HTTP**(Pi가 서버).
계약은 [`docs/protocol.md`](docs/protocol.md)가 단일 진실 — iPad·Pi 양쪽과 함께만 변경한다.

## 빌드·테스트

```bash
# Pi (uv)
cd pi && uv sync && uv run pytest -q          # mock 기반, 하드웨어 불필요 (64 테스트)

# iPad 코어
cd ios && swift test                          # 프로토콜·coordinator·분류 (45 테스트)

# iPad 앱
cd ios/App && xcodegen generate
xcodebuild -project Trasher.xcodeproj -scheme Trasher -destination 'generic/platform=iOS Simulator' build

# 데모 (하드웨어 없이 전체 사이클 시연)
xcrun simctl launch <udid> kr.recycle.trasher.Trasher --demo
```

## 설계 원칙

- **하드웨어/비전/BLE는 인터페이스 + Mock으로 추상화** → macOS/CI에서 전 로직 테스트, 실기기 검증만 분리.
- **분류 카테고리 정규화는 iPad 책임** — 외부 API 라벨 → 3분류 + confidence 임계값. Pi엔 3분류만 전달.
- **분류 API는 추상화 뒤** — 미정이라 `MockClassificationService`로 개발, 확정 시 `RemoteClassificationService`만 교체.
- **타임아웃·끊김 폴백** — 어떤 경우에도 Pi는 결과를 받는다(`기타` 안전 기본값).

## 현황

| 구성 | 상태 |
|---|---|
| Pi 제어 프로그램 | ✅ 구현 완료 (mock 테스트·codex 리뷰). 실기기 브링업(bless/서보/카메라)만 잔여 |
| 프로토콜 스펙 | ✅ proto v1 동결, Python↔Swift 교차언어 계약 테스트 |
| iPad 앱 | ✅ 구현 완료 (코어 테스트·iOS 빌드·런타임 검증). 실 BLE 통합·실 분류 API만 잔여 |

잔여는 전부 **실물 하드웨어** 또는 **외부 API 확정** 의존. 작업 추적은 beads(`bd ready`).
개발 사이클은 [`docs/dev-cycle.md`](docs/dev-cycle.md), 에이전트 가이드는 [`CLAUDE.md`](CLAUDE.md).
