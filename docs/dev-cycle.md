# 개발 사이클 설계 (ralph-loop 도달목표 + promise 종료)

이 프로젝트는 **기획→설계→구현→테스트→리뷰** 5단계를 한 작업 단위(beads 이슈)마다 반복하는
ralph-loop 방식으로 진행한다. 각 마일스톤의 모든 이슈가 닫히고 품질 게이트를 통과하면
`<promise>...</promise>` 종료 메시지를 출력해 루프를 끝낸다.

## 마일스톤 순서 (도달목표)

```
M1. Pi 스캐폴딩      → <promise>PI_SCAFFOLD_COMPLETE</promise>
M2. 스펙 정의(동결)  → <promise>SPEC_FROZEN</promise>
M3. iPad 앱          → <promise>IPAD_COMPLETE</promise>
전체 완료            → <promise>ALL_COMPLETE</promise>
```

순서 근거: Pi가 계약(`docs/protocol.md`)의 Peripheral 측을 먼저 구현·검증하며 스펙을 굳히고,
그 동결된 스펙을 iPad(Central)가 소비한다.

## 5단계 사이클 (이슈 1개당)

| 단계 | 활동 | 도구 |
|---|---|---|
| **기획** | `bd ready`로 다음 이슈 선택 → `bd update <id> --claim` → 수용기준 확인 | beads |
| **설계** | `docs/protocol.md` 계약 확인, 모듈/인터페이스 설계. 외부지식 필요 시 리서치 | `@multi-agent-tools:gemini-research`, `gemini-analyze` |
| **구현** | 코드 작성. 반복적 build-fix는 위임. iPad UI는 디자인 스킬 | `@multi-agent-tools:codex-implement`, `@frontend-design`(iPad) |
| **테스트** | macOS에서 mock 기반 pytest / iOS 빌드. 통과까지 반복 | pytest, ruff, mypy / xcodebuild |
| **리뷰** | 교차검증(2차 의견) + 자체 리뷰. 통과 시 `bd close` + commit | `@multi-agent-tools:codex-review`, `/code-review` |

> **핵심 원칙:** Pi 하드웨어 의존(picamera2/gpiozero/bless)은 Linux 전용이므로,
> 모든 하드웨어·비전·BLE는 **인터페이스 + Mock**으로 추상화해 macOS/CI에서 전 사이클을 테스트한다.
> 실기기 검증만 Pi에서 수행한다.

## ralph-loop 통합

ralph-loop는 Stop 훅이 같은 프롬프트를 반복 투입하고, 모델은 파일·git 이력에 남은
자신의 이전 작업을 보고 점증적으로 완성한다. 본 세션은 `/goal` Stop 훅이 이미 루프 드라이버
역할을 하므로, 그 위에 promise 종료 규약을 얹는다.

**반복 프롬프트(개념):**
```
docs/dev-cycle.md의 5단계 사이클을 따른다.
1) bd ready로 현재 마일스톤의 다음 이슈를 잡는다(없으면 마일스톤 promise 출력).
2) 설계→구현→테스트→리뷰를 수행하고 테스트를 통과시킨다.
3) bd close + 커밋.
현재 마일스톤의 모든 이슈가 닫히고 품질 게이트 통과 시 해당 <promise> 출력.
```

**종료(promise) 판정 기준:**
- M1: Pi 이슈 전부 `closed` + `pytest`/`ruff`/`mypy` 그린 → `PI_SCAFFOLD_COMPLETE`
- M2: protocol 상수 Python↔문서 동기 검증 + 계약 테스트 통과 → `SPEC_FROZEN`
- M3: iPad 타깃 빌드 성공 + 핵심 UI 흐름 동작 → `IPAD_COMPLETE`

## 품질 게이트

- Pi: `ruff check`, `mypy`, `pytest` 전부 통과(모두 mac에서 mock으로 실행 가능).
- 커밋 단위: 이슈 1개 = 1커밋(가능하면). 메시지에 `(trash-xxx)` 이슈 ID 포함.
- 세션 종료 시 `git push`(CLAUDE.md 세션 프로토콜 준수).
