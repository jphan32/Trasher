# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

순환자원 홍보용 프로토타이핑 프로젝트. 가칭 **"AI 쓰레기 자동 분류기"** (제목은 변경될 수 있음). 전시/체험 부스에서 참여자가 쓰레기를 투입하면, AI가 종류를 판별하고 컨베이어 벨트가 자동으로 분류한 뒤, 보상으로 씨앗 상품을 제공하는 인터랙티브 데모.

이 저장소는 **모노레포**다. 두 구성 요소(iPad 앱, Pi 제어 프로그램)와 공유 문서가 한 저장소에 위치한다.

```
/ios    iPad 앱 (Swift / SwiftUI / CoreBluetooth)
/pi     Raspberry Pi 제어 프로그램 (Python) — 비전·서보·BLE + 사진/분류 HTTP
/docs   프로토콜·설계 문서 (단일 진실 공급원)
```

분류(Gemini)는 **Pi의 HTTP 엔드포인트 `POST /classify/{cycle}`** 로 통합돼 있다(`pi/src/trash_sorter/classify/`). iPad는 이미지 대신 cycle ID만 보내고 Pi가 로컬 사진을 읽어 Gemini를 호출한다(트래픽 최소화).

프로토콜 상수(GATT UUID, enum 등)는 `docs/protocol.md`를 단일 진실로 두고 Swift·Python 양쪽에 **수동 동기화**한다(프로토타입 단계). 한쪽을 바꾸면 반드시 양쪽과 문서를 함께 갱신한다.

## 기술 스택 (확정)

| 구성 요소 | 스택 |
|---|---|
| **iPad 앱** | Swift / SwiftUI / **CoreBluetooth (Central 역할)** / URLSession(HTTP) |
| **Raspberry Pi** | Python 3 / **picamera2 + OpenCV**(카메라·비전) / **gpiozero**(서보·벨트 GPIO) / **bless**(BLE Peripheral, BlueZ/dbus) |
| **사진 전송** | 제어·상태 = BLE 상시 연결 / **사진 = 로컬 WiFi HTTP** (Pi → iPad) |
| **분류 API** | **Gemini 3.5 Flash** (Generative Language API, structured output). Pi의 `POST /classify/{cycle}`에 통합 — Pi가 SA 키 보유·로컬 사진 읽어 호출. **호출자/결과 핸들러는 iPad**(UI 표시 + BLE 제어 주도), Pi는 Gemini 위임 실행자. **재활용 팁(description)** 을 함께 받아 iPad가 표시. |

- **BLE 역할 고정:** iPad = Central(연결 주체, 스캔·연결), Raspberry Pi = Peripheral(GATT 서비스 광고). 이 방향은 바뀌지 않는다.
- iPad 앱 개발에는 macOS + Xcode가 필요하며 실제 BLE 검증은 시뮬레이터가 아닌 **실기기(iPad)** 에서만 가능하다.

## 시스템 아키텍처 (핵심)

전체 동작은 **iPad 앱 ↔ Raspberry Pi ↔ 외부 분류 API** 3자 간 협업으로 구성된다. 어느 한쪽 코드만 봐서는 전체 흐름을 알 수 없으므로, 두 구성 요소의 역할 분담과 메시지 흐름을 먼저 이해해야 한다.

**두 개의 통신 채널이 공존한다:** ① 제어·상태·결과는 **BLE**(상시 연결), ② 사진 같은 큰 데이터는 **로컬 WiFi HTTP**. Pi가 사진 촬영을 마치면 BLE notification으로 "사진 준비됨 + 사진 URL/ID"를 보내고, iPad가 그 URL로 HTTP GET 한다. iPad가 Pi의 주소를 알 수 있도록 Pi의 `IP:port`도 BLE 특성(characteristic)으로 노출한다.

### 구성 요소

1. **iPad 앱** — 사용자 대면 컨트롤러 & 시각화 화면
   - Raspberry Pi 장치와 **BLE로 상시 연결을 유지**하며 제어한다. (연결 끊김/재연결 처리가 중요)
   - Raspberry Pi로부터 받은 쓰레기 사진을 **외부 서버 API**로 보내 종류를 판별한다.
   - 판별 결과를 Raspberry Pi로 다시 전달한다.
   - 전체 진행 과정을 참여자가 볼 수 있도록 **시각적으로 표현**한다.
   - 분류 완료 후 **간단한 유저 인터랙션**으로 씨앗 5종 중 1개를 선정·표시하여 참여자에게 제공한다.

2. **Raspberry Pi 제어 프로그램** — 하드웨어 제어 & 비전 트리거
   - 카메라 영상의 **변이(motion/변화)를 추적**하다가 쓰레기 투입을 검출하면 사진을 촬영해 iPad 앱으로 전송한다.
   - iPad로부터 분류 결과를 **수신할 때까지 대기**한다 (동기적 흐름).
   - 결과를 **"페트" / "캔" / "기타" 3가지**로 분류하고, 그에 맞게 **서보 모터로 이동 경로를 제어**한 뒤 **컨베이어 벨트를 구동**해 쓰레기를 분리수거함으로 이동시킨다.
   - 물리 구성: **서보 3개**(게이트 1=정위치 홀드, 분기 2=좌/우, 둘 다 닫힘=중앙) + **벨트 모터 1**(시간 기반 완료). 시퀀스·매핑은 `docs/protocol.md` §2.5, 배선·핀맵·BOM은 `docs/hardware.md`, **Pi 4B OS 설치·패키지·설정 전체 절차는 `docs/pi-setup.md`**.

3. **외부 분류 API** — 이미지 → 쓰레기 종류 판별 (외부 서버, iPad 앱이 호출)

### 동작 시퀀스 (1회 분류 사이클)

```
[Pi]   카메라 변이 감지 → 쓰레기 투입 검출 → 사진 촬영(picamera2)
[Pi]   BLE notification: "사진 준비됨 + URL/ID" → 결과 대기
[iPad] BLE 알림 수신 → 해당 URL로 사진 HTTP GET (로컬 WiFi)
[iPad] ClassificationService(분류 API) 호출 → 종류 판별 → 3분류로 정규화
[iPad] 진행 과정 시각화 → 결과(페트/캔/기타)를 BLE로 Pi에 전송
[Pi]   결과 수신 → 서보 모터로 경로 설정 → 컨베이어 벨트 구동 → 이동 완료
[iPad] 분류 완료 → 씨앗 5종 중 1개 랜덤 추첨 인터랙션 → 참여자에게 제공
```

> **사이클 게이팅:** iPad가 결과/씨앗 화면에 있는 동안 `Command{stop}`으로 Pi 감지를 멈추고, 어트랙트 화면 복귀 시 `Command{start}`로 재개한다. iPad가 인테이크 타이밍을 통제하므로 참여자 간 흐름이 겹치지 않는다. (`docs/protocol.md` §2.1)

## 핵심 설계 고려사항

- **BLE GATT 스펙이 두 구성 요소의 계약(contract)이다.** 제어 명령, 분류 결과, 상태/하트비트, "사진 준비됨" 알림, Pi의 `IP:port` 등 특성(characteristic) 정의를 한쪽에서 바꾸면 반드시 iPad·Pi 양쪽을 함께 수정해야 한다. (구현 전 이 GATT 스펙부터 확정할 것)
- **사진은 BLE로 보내지 않는다.** 제어 신호만 BLE, 사진 바이너리는 WiFi HTTP. BLE로 사진을 청크 전송하려 하지 말 것 — 느리고 불안정하다.
- **분류 카테고리 정규화는 iPad 책임.** 외부 API의 출력 라벨과 Pi가 처리하는 3분류("페트"/"캔"/"기타")는 다를 수 있다. API 라벨 → 3분류 매핑을 iPad의 `ClassificationService` 계층에서 수행하여 Pi에는 항상 3가지 중 하나만 전달한다.
- **분류 API는 추상화 뒤에 둔다.** iPad에 `ClassificationService.classify(cycle:on:)` + `MockClassificationService`(개발/데모) / `PiClassificationService`(실서비스: Pi `POST /classify/{cycle}` 호출). 앱의 나머지 코드는 mock/real을 구분하지 않는다.
- **분류 키는 서버 측(Pi)에.** GCP 서비스 계정 키(`secret/`, gitignore됨)는 배포 iPad에 넣지 않는다. **Pi가 키를 보유**하고 로컬 사진을 읽어 Gemini를 호출한다(`/classify` 엔드포인트). iPad는 cycle ID만 보내고 결과를 핸들링(이미지 재업로드 없음 → 트래픽 최소화). Pi에 인터넷이 필요 — 합의된 "인터넷 공유 라우터" 구조 전제(Pi-as-AP 아님).
- **재활용 팁은 iPad 전용 표시.** Gemini가 3분류와 함께 반환하는 `description`(재활용 팁)은 BLE로 Pi에 보내지 않고(Pi는 3분류만 필요) iPad reward 화면에 부가정보로만 표시한다. BLE 계약 불변.
- **동기적 대기 흐름.** Pi는 결과를 받을 때까지 멈춰 대기하므로, 타임아웃/에러(HTTP 실패, API 실패, BLE 끊김) 시 폴백 동작("기타"로 처리 등)을 정의해야 한다.
- **상시 연결 유지.** 전시 환경에서 장시간 무인 운영되므로 BLE 재연결·WiFi 재연결·상태 복구가 안정성의 핵심이다.

## 프로토콜 스펙 (계약 문서)

**`docs/protocol.md`** 가 iPad·Pi 사이 BLE GATT 스펙과 분류 결과 데이터 모델의 **단일 진실 공급원**이다. 통신/데이터 모델을 건드리는 작업은 반드시 이 문서를 먼저 읽고, 변경 시 양쪽 구현과 함께 갱신한다. 요점:

- GATT 서비스 1개 + 특성 6개(DeviceInfo / Status / PhotoReady / ClassificationResult / Command / CommandAck). 페이로드는 모두 UTF-8 JSON.
- 상태머신은 **Pi가 소유**, `Status` notify로 노출(+ `seq` 하트비트). 사진–결과 짝은 `cycle` ID로 상관시키며 불일치 시 폐기.
- 3분류 enum: `pet`/`can`/`other`(`other`는 안전 기본값). API 라벨→3분류 정규화와 confidence 임계값은 iPad `ClassificationService`가 담당.
- 타임아웃 시 양쪽 모두 `other`로 폴백 — Pi는 어떤 경우에도 결과를 받는다.

## 빌드/테스트 명령

### Pi (`/pi`) — Python, **uv로 환경 관리**

Python 환경·의존성은 반드시 **uv**로 관리한다(`pip`/`python -m venv` 직접 사용 금지). 모든 하드웨어/비전/BLE는 인터페이스+Mock으로 추상화돼 있어 **macOS에서 전 테스트가 통과**한다.

```bash
cd pi
uv sync               # .venv + 크로스플랫폼 의존성 + dev 도구([dependency-groups])
uv run pytest -q      # 테스트(전부 mock 기반)
uv run ruff check .   # 린트
uv run mypy           # 타입체크
uv run trash-sorter   # 실행(실기기)
```

- 하드웨어 의존(picamera2/gpiozero/bless)은 **Linux 전용 sdist라 macOS uv 해석을 깨뜨린다**. 따라서 pyproject가 아니라 `pi/requirements-pi.txt`로 분리하고, Pi에서만 `uv pip install -r requirements-pi.txt`로 설치한다.
- 새 의존성 추가는 `uv add <pkg>`(런타임) / `uv add --dev <pkg>`(개발). `uv.lock`은 커밋한다.

### iPad (`/ios`) — Swift/SwiftUI

2계층: **`TrasherCore`**(SwiftPM 라이브러리, 순수 로직 — 호스트 `swift test`로 검증) + **Xcode 앱 타깃**(`ios/App`, SwiftUI/CoreBluetooth, XcodeGen 생성).

```bash
cd ios && swift test                 # 코어 검증(프로토콜/분류/coordinator/프레젠테이션/스테퍼, 59 테스트)
cd ios/App && xcodegen generate      # project.yml → Trasher.xcodeproj (.xcodeproj는 gitignore)
xcodebuild -project Trasher.xcodeproj -scheme Trasher -destination 'generic/platform=iOS Simulator' build
```

- 코어 로직(`SessionCoordinator` = 게이팅/정합화/폴백, 분류 정규화, 프레젠테이션)은 전부 mock으로 호스트 테스트. `BLECentral`(CoreBluetooth)·SwiftUI 렌더링은 실기기/시뮬레이터 검증.
- 분류: 개발/데모는 `MockClassificationService`, 실서비스는 `PiClassificationService`(→ Pi `POST /classify/{cycle}`). `--demo`는 카테고리·팁이 회전하는 `DemoClassifier` 사용.

### 분류 엔드포인트 (Pi `/pi`, `classify/` 모듈)

- `POST /classify/{cycle}` → Pi가 로컬 `/photos/{cycle}.jpg`를 읽어 Gemini 3.5 Flash(structured output)로 분류 → `{category, description, confidence}`. SA 키(`TRASH_GEMINI_CREDENTIALS`) 없으면 `MockClassifier`(dev/sim).
- structured output(`responseSchema`)으로 스키마 보장. 프롬프트는 `pi/prompts.toml`(시스템 지침+분류 프롬프트)로 코드와 분리.
- 키 경로 env: `TRASH_GEMINI_CREDENTIALS`. `secret/`는 gitignore — 절대 커밋 금지. 라이브 검증은 키+인터넷 필요.

## 개발 워크플로 메모

- 상세 설계는 개발 진행 중 사용자가 추가로 전달한다. 통신/데이터 모델 변경 전 `docs/protocol.md`를 먼저 갱신한다.
- 개발 사이클(기획-설계-구현-테스트-리뷰, ralph-loop 도달목표/`<promise>` 종료)은 `docs/dev-cycle.md` 참조.


<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:7510c1e2 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->
