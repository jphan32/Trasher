# BLE GATT 스펙 & 분류 결과 데이터 모델

iPad 앱(BLE **Central**)과 Raspberry Pi 제어 프로그램(BLE **Peripheral**) 사이의 **계약 문서**.
이 파일을 바꾸면 iPad·Pi 양쪽 구현을 반드시 함께 수정한다.

- `proto` 버전: **1**
- 인코딩: 모든 특성(characteristic) 값은 **UTF-8 JSON**. 사진 같은 바이너리는 BLE로 보내지 않고 WiFi HTTP로 전송한다(아래 "사진 채널" 참조).
- 통신 채널: ① 제어·상태·결과 = **BLE**(상시 연결) / ② 사진 = **로컬 WiFi HTTP**.

### 사진 채널 (HTTP)
- **HTTP 서버는 Raspberry Pi에서 호스팅**한다. iPad는 클라이언트(GET pull). 이유: Pi는 상시 켜진 Linux로 견고하게 서버를 띄울 수 있는 반면, iOS 앱은 앱 생명주기(백그라운드/suspend)에 종속되어 서버 호스팅에 부적합하기 때문. 타이밍은 BLE `PhotoReady` 알림이 조율한다.
- **네트워크 구성**: iPad·Pi 모두 **인터넷(WAN)이 연결된 동일 WiFi 라우터의 DHCP 클라이언트**(Pi-as-AP 아님). iPad는 라우터의 **LAN으로만 Pi와 통신**한다(사진 GET + 분류 `POST /classify/{cycle}`). **인터넷(Gemini 호출)은 Pi가** 사용한다 — iPad는 분류 API를 직접 부르지 않는다. iPad가 "Pi의 WiFi"에 붙는 게 아니라, 둘 다 같은 라우터에 붙어 LAN 안에서 peer로 통신한다. Pi는 받은 IP를 BLE `DeviceInfo`로 보고하므로 별도 디스커버리가 불필요하다.
- **권장 운영**: 부스 인터넷이 불안정할 수 있으므로 **인터넷을 공급하는 전용 휴대용 라우터**(이더넷/테더링/SIM으로 WAN 공급)를 지참해 iPad·Pi를 거기에 붙이면 장소 네트워크와 무관하게 이 구조를 안정적으로 유지할 수 있다.
- **IP 안정화**: 라우터에서 Pi MAC에 **DHCP 예약(고정 임대)** 권장. 보조로 mDNS(`sorter-01.local`) 사용 가능.
- ⚠️ 라우터의 **AP/Client Isolation(단말 간 격리)을 OFF**, iPad·Pi가 **같은 서브넷**에 있어야 LAN HTTP가 동작한다.
- 사진·분류 호출은 **LAN 내부**(iPad↔Pi). 인터넷은 **Pi→Gemini**(`/classify` 내부) 호출에만 사용 — 인터넷이 끊겨도 사진 전송·BLE 제어는 동작하고 분류만 영향받는다(Pi가 Mock/타임아웃 폴백).

---

## 1. GATT 구조

UUID는 이 프로젝트 전용 placeholder다. 배포 전 재생성하려면 `uuidgen`으로 새로 만들되 **base(뒤 24자리)는 고정**하고 앞 8자리의 `…01xx` 부분만 구분자로 쓴다. 양쪽 코드에서 동일 상수를 공유한다.

**Service:** `4F520100-7A69-4B43-8E2D-1C9A7F3B0001`

| 특성 | UUID | 속성 | 방향 | 용도 |
|---|---|---|---|---|
| DeviceInfo | `4F520101-…` | Read | Pi→iPad | 펌웨어·프로토콜 버전, HTTP `ip:port`, 장치명 |
| Status | `4F520102-…` | Notify, Read | Pi→iPad | 상태머신 상태 + 하트비트(`seq`) |
| PhotoReady | `4F520103-…` | Notify | Pi→iPad | 사진 촬영 완료 알림(cycle + HTTP path) |
| ClassificationResult | `4F520104-…` | Write (w/ response) | iPad→Pi | 분류 결과(3분류 + confidence) |
| Command | `4F520105-…` | Write (w/ response) | iPad→Pi | 제어 명령(start/stop/reset/…) |
| CommandAck | `4F520106-…` | Notify | Pi→iPad | Command 처리 결과 ack |

> `…` 부분은 service의 base와 동일: `7A69-4B43-8E2D-1C9A7F3B0001`

### 광고(Advertising) & 연결
- Pi는 **연결되어 있지 않을 때 항상** Service UUID + local name(예: `sorter-01`)을 광고한다. 연결되면 광고 중지, 끊기면 재개.
- **동시에 1개 Central(iPad)만** 연결한다.
- iPad는 Service UUID로 스캔→연결한다(이름 의존 X).

### 연결 직후 브링업 순서 (iPad)
1. Service UUID로 스캔 → 연결 → 특성 디스커버리
2. **DeviceInfo Read** → `proto` 버전 호환 확인(불일치 시 사용자 경고) → `ip:port` 저장
3. Status / PhotoReady / CommandAck **구독(CCCD 활성화)**
4. `Command{cmd:"start"}` 전송 → 정상 운영
5. 끊기면 자동 재연결 → (디스커버리/구독 재수행) → 상태 복구

---

## 2. 상태 머신 (Pi 소유)

Status 특성으로 노출. 상태 전이가 일어날 때마다, 그리고 **최소 2초마다(하트비트)** notify한다. 매 notify마다 `seq`를 +1 한다. iPad는 `seq`가 N초(예: 6초) 이상 멈추면 BLE 링크가 살아 있어도 "Pi 멈춤"으로 간주한다.

```
              ┌─────────────────────── reset / 완료 ───────────────────────┐
              │                                                            │
  idle ──검출──> detecting ──안정──> capturing ──촬영완료──> awaiting_result │
   ▲                                                              │        │
   │                                            결과수신/타임아웃  ▼        │
   └──────────────────────────────── sorting <───────────────────┘────────┘
                                       (서보+벨트 구동)

  any ──estop/오류──> error ──reset──> idle
  any ──maintenance(true)──> maintenance ──maintenance(false)──> idle
```

| state | 의미 |
|---|---|
| `idle` | 투입 대기(카메라 변이 감시 중) |
| `detecting` | 변이 감지, 안정화 대기 |
| `capturing` | 사진 촬영 중 |
| `awaiting_result` | 사진 준비됨, iPad의 분류 결과 대기(타임아웃 타이머 동작) |
| `sorting` | 결과대로 서보 경로 설정 + 컨베이어 벨트 구동 중 |
| `error` | 하드웨어/내부 오류(아래 에러 코드) |
| `maintenance` | 수동 정지/점검 모드 |

> 보상(에코포인트 표시·막대사탕 지급, §4.6)은 **iPad 전용 인터랙션**이라 Pi 상태머신에 없음. `sorting` 완료 후 Pi는 `idle`로 복귀.

### 2.1 사이클 게이팅 (iPad가 다음 사이클 시작을 통제)
Pi는 **"started" 상태일 때만** 변이를 감지한다. iPad가 결과/보상 인터랙션 화면에 들어가면 `Command{stop}`, 어트랙트(대기) 화면으로 복귀하면 `Command{start}`를 보낸다. 이렇게 해야 참여자 A의 보상 수령 중에 Pi가 B의 투입을 감지하는 화면·물리 흐름 어긋남을 막는다. 즉 **iPad가 인테이크 타이밍의 오케스트레이터**다.

### 2.2 결과–타임아웃 정합화 (reconciliation)
iPad는 `ClassificationResult`를 보낸 뒤 곧바로 Pi의 Status 전이를 확인한다. Pi가 같은 `cycle`로 `sorting`에 들어갔고 `lastSort`가 보낸 값과 같으면 정상. 만약 Pi가 먼저 타임아웃(`result_timeout`)으로 `other` 처리했다면 cycle은 맞아도 `lastSort`가 `other`다 — 이 경우 iPad UI는 "기타로 처리됨"으로 **정정 표시**한다. (Pi의 실제 동작이 진실)

---

## 2.5 물리 제어 모델 (Pi 하드웨어)

3개 서보 + 1개 컨베이어 벨트 모터로 구성. gpiozero로 제어.

| 액추에이터 | 역할 |
|---|---|
| **게이트 서보** ×1 | 투입물을 캡처 존에 **정위치 정지·홀드**. 사진 촬영~결과 대기 동안 닫힘, 결과 확정 후 열어 분기 경로로 방출 |
| **분기 서보 좌** ×1 | 열림 → 좌측 경로 |
| **분기 서보 우** ×1 | 열림 → 우측 경로 |
| (좌·우 모두 닫힘) | → **중앙 경로** |
| **벨트 모터** ×1 | 컨베이어 구동(시간 기반: 고정 시간 구동 후 완료) |

**카테고리 → 경로 매핑** (Pi 설정값, 물리 배치에 맞게 조정. 기본 제안):
```
pet   → 좌측 경로 (분기서보 좌 열림, 우 닫힘)
can   → 우측 경로 (분기서보 우 열림, 좌 닫힘)
other → 중앙 경로 (좌·우 모두 닫힘)
```

**`sorting` 시퀀스 (시간 기반 완료):**
```
1. 결과 수신 → category에 맞게 분기 서보 좌/우 설정
2. 게이트 서보 열림 → 투입물 방출
3. 벨트 모터 구동(고정 시간 T_belt, 예: 3s)
4. T_belt 경과 → 벨트 정지, 게이트 서보 닫힘, 분기 서보 중앙(닫힘)으로 복귀
5. idle 복귀(단, iPad가 stop 했다면 started 될 때까지 감지 안 함 §2.1)
```
- `capturing` 동안 게이트 서보는 **닫힘**(홀드) 상태로 투입물을 캡처 존에 고정한다.
- `Command{sort, arg:cat}`(테스트용)도 위 시퀀스를 그대로 수행한다.
- `T_belt`, 서보 구동(연속회전 저속·시간), 매핑은 모두 Pi 설정값(튜닝 대상).

---

## 3. 특성별 페이로드 스키마

JSON 키는 짧게 유지하되 가독성을 우선한다. 모든 메시지는 MTU 협상 후 단일 notify/write에 들어가는 크기(< ~180 B)를 유지한다.

> **null 생략 규약:** 값이 `null`인 optional 필드(`err`, `lastSort`, `arg`, `raw`, `w`/`h`/`ts` 등)는 **키 자체를 생략**해 보낸다. 수신 측은 **키 부재 ≡ null**로 처리한다(Swift `Codable` optional은 키 부재 시 자동 `nil`). 아래 예시의 `null`은 의미 설명용이며 와이어에는 해당 키가 없을 수 있다.

### 3.1 DeviceInfo (Read)
```json
{ "fw": "0.1.0", "proto": 1, "ip": "192.168.4.1", "port": 8080, "name": "sorter-01" }
```
- `proto`: 프로토콜 버전(정수). iPad와 불일치 시 경고/차단.
- `ip`,`port`: Pi의 사진 HTTP 서버 주소. Pi가 공유 라우터에서 받은 **DHCP IP를 그대로 보고**한다. 라우터에서 **DHCP 예약**을 걸면 사실상 고정 → 재연결 시 재조회 불필요. (자세한 네트워크 전제는 상단 "사진 채널" 참조)

### 3.2 Status (Notify, Read)
```json
{ "state": "sorting", "cycle": 42, "seq": 1083, "err": null, "lastSort": "can" }
```
- `state`: §2의 상태 문자열
- `cycle`: 현재 사이클 ID(없으면 `0`)
- `seq`: 단조 증가 하트비트 카운터(매 notify마다 +1)
- `err`: 에러 코드(§5) 또는 `null`
- `lastSort`: **현재 cycle**의 분류·이동 결과(`pet`/`can`/`other`/`null`) — 시각화용. **cycle-scoped**: 새 cycle 시작(detecting)·reset·maintenance·error 시 `null`로 초기화되고, sort 시에만 설정된다. 따라서 `idle` + 일치 `cycle` + `lastSort` 존재 ⇒ "이 cycle이 실제로 sort 완료됨"을 의미(중단된 cycle은 `lastSort`가 없어 오인 reward를 막는다).

### 3.3 PhotoReady (Notify)
```json
{ "cycle": 42, "path": "/photos/42.jpg", "w": 1280, "h": 720, "ts": 1696000000 }
```
- `cycle`: 상관 ID. iPad는 결과 전송 시 이 값을 그대로 echo.
- `path`: HTTP 경로. iPad는 DeviceInfo의 `ip:port`와 합쳐 `http://{ip}:{port}{path}`로 GET.
- `w`,`h`: 픽셀 크기(시각화/레이아웃용, 선택)
- `ts`: Pi epoch seconds(로깅용, 선택)

### 3.4 ClassificationResult (Write w/ response)
iPad → Pi. 자세한 데이터 모델은 §4.
```json
{ "cycle": 42, "category": "pet", "confidence": 0.93, "raw": "PET_bottle" }
```
- `cycle`: **반드시 Pi의 현재 `awaiting_result` cycle과 일치**해야 함. 불일치(=오래된 결과)면 Pi가 폐기.
- `category`: `pet` | `can` | `other`
- `confidence`: 0.0–1.0
- `raw`: 원본 API 라벨(선택, 로깅/시각화용)

**Pi 처리:** 유효 결과 수신 → `sorting`으로 전이(해당 cycle의 `category`대로 서보/벨트 구동) → 완료 후 `idle`. cycle 불일치 또는 `awaiting_result`가 아닐 때 수신하면 무시(Write는 ATT 레벨에서 ack됨).

### 3.5 Command (Write w/ response)
```json
{ "cmd": "start", "arg": null, "id": 7 }
```
- `id`: ack 상관용 명령 ID(iPad가 단조 증가로 부여)
- `cmd` / `arg`:

| cmd | arg | 동작 |
|---|---|---|
| `start` | — | 검출 시작/재개(→ idle에서 감시) |
| `stop` | — | 검출 일시정지 |
| `reset` | — | 현재 사이클 중단 → idle |
| `sort` | `"pet"`/`"can"`/`"other"` | 수동 분류(테스트용, 즉시 서보+벨트) |
| `belt` | `"fwd"`/`"stop"` | 벨트 수동 구동/정지(테스트) |
| `calibrate` | — | 서보 캘리브레이션 |
| `maintenance` | `"true"`/`"false"` | 점검 모드 진입/해제 (arg는 항상 문자열 — `Command.arg`는 String?) |
| `estop` | — | 비상 정지(모든 모터 즉시 정지 → error) |

### 3.6 CommandAck (Notify)
```json
{ "id": 7, "ok": true, "err": null }
```
- `id`: 대응 Command의 `id`
- `ok`: 처리 성공 여부
- `err`: 실패 시 에러 코드(§5)

---

## 4. 분류 결과 데이터 모델

### 4.1 3분류 enum
```
pet   → "페트"   (PET 플라스틱병)
can   → "캔"     (알루미늄/철 캔)
other → "기타"   (그 외 전부 + 불확실)
```
`other`는 **안전 기본값(catch-all)**이다. pet/can 확신이 없으면 항상 `other`로 보낸다. (캔을 페트함에 잘못 넣는 것보다 기타로 보내는 편이 낫다.)

### 4.2 Swift (iPad)
```swift
enum WasteCategory: String, Codable {
    case pet, can, other            // 페트, 캔, 기타
}

struct ClassificationResult: Codable {
    let cycle: UInt32
    let category: WasteCategory
    let confidence: Double           // 0.0 ... 1.0
    let raw: String?                 // 원본 API 라벨(로깅용)
}
```

### 4.3 Python (Pi)
```python
from enum import Enum
class WasteCategory(str, Enum):
    PET = "pet"; CAN = "can"; OTHER = "other"
```

### 4.4 분류 = Gemini 3.5 Flash (Pi `/classify/{cycle}`) + 재활용 팁
분류는 **Gemini 3.5 Flash**가 structured output(responseSchema)으로 수행하며, **Pi의 HTTP 엔드포인트**에
통합돼 있다: `POST /classify/{cycle}`. iPad는 이미지 대신 **cycle ID만** 보내고, Pi가 이미 보유한 로컬
사진(`/photos/{cycle}.jpg`)을 읽어 Gemini를 호출한다(이미지 재업로드 없음 → 트래픽 최소화). 키(SA)는 Pi가
보유한다. **호출자/결과 핸들러는 iPad**(UI 표시 + BLE 3분류 전달 주도), Pi는 Gemini 위임 실행자.

응답: `{ "category": "pet|can|other", "description": "<재활용 팁(한국어)>", "confidence": 0.0~1.0, "eco_points": 0~100, "recyclable": true|false }`
- `category`는 Gemini가 enum으로 직접 3분류 출력 → iPad `CategoryNormalizer`는 매핑+임계값(기본 0.50)으로
  한 번 더 안전 정규화(불확실/미지 → `other`). **Pi는 항상 3분류만 받는다.**
- `description`(재활용 팁)은 **BLE로 Pi에 보내지 않는다**(Pi는 3분류만 필요). iPad가 reward 화면에
  부가정보로만 표시한다. 따라서 BLE `ClassificationResult`(§3.4) 계약은 불변.
- `eco_points`(정수 0~100): Gemini가 **제출물의 재활용 시 탄소절감 효과를 수치화**한 에코포인트.
  재활용이 불가한 일반 쓰레기는 `0`. iPad reward 화면이 이 값을 표시하고 사탕 수를 산출한다(§4.6).
- `recyclable`(불리언): 제출물이 재활용 가능한지 여부. **`category=other`라도 `recyclable=true`이면**
  (예: 종이·유리 등) 에코포인트를 측정하고 굿즈를 제공한다. 일반 쓰레기는 `false` + `eco_points=0`.
- `eco_points`·`recyclable`도 `description`과 동일하게 **iPad 전용 표시·보상 정보로 BLE에 보내지 않는다.**
  BLE `ClassificationResult`(§3.4) 계약은 불변(Pi는 3분류로만 물리 분류). Gemini→`/classify` HTTP 응답에만 존재.

### 4.5 추상화 계층
```swift
protocol ClassificationService {
    func classify(cycle: Int, on device: DeviceInfo) async throws -> RawClassification  // {label, confidence, description?, ecoPoints?, recyclable?}
}
// MockClassificationService : 개발/데모용(고정/회전 결과 + 캔드 팁 + eco)
// PiClassificationService   : Pi POST /classify/{cycle} 호출(주소는 DeviceInfo에서 도출)
```
앱의 나머지 코드는 mock/real을 구분하지 않는다. §4.4 정규화는 이 계층 내부에서 수행한다.
팁(`description`)은 `SessionCoordinator.onTip` → iPad UI로 흐른다(Pi 미전달, BLE 계약 불변).
에코포인트/재활용 여부는 `SessionCoordinator.onEcoReward`(§4.6 `EcoReward`) → iPad UI로 흐른다(동일하게 Pi 미전달).

### 4.6 보상 모델 (iPad 전용) — 막대사탕 + 에코포인트
보상은 **씨앗 추첨이 아니라** 에코포인트 기반 **막대사탕 1~2개**다(랜덤 아님, `eco_points`에서 결정적 산출).
`SeedReward`는 폐기하고 `EcoReward`로 대체한다. BLE 계약과 무관(iPad UI 전용).

```swift
struct EcoReward {
    let ecoPoints: Int        // Gemini가 산출한 탄소절감 에코포인트(0~100)
    let recyclable: Bool      // 재활용 가능 여부(other라도 true면 보상)
    let lollipops: Int        // 지급 막대사탕 수: 0 / 1 / 2 (아래 규칙)
}
```

**산출 규칙(임계값은 튜닝 대상, 기본):**
```
recyclable == false  또는  eco_points <= 0   → lollipops = 0  (일반 쓰레기, 굿즈 없음)
0 < eco_points < 50                          → lollipops = 1
eco_points >= 50                             → lollipops = 2
```
- pet/can은 항상 재활용 가능 → eco_points > 0 → 최소 1개.
- `category=other` + `recyclable=true`(종이·유리 등)도 eco_points 측정·굿즈 제공.
- `category=other` + `recyclable=false`(일반 쓰레기)는 eco_points=0 → 사탕 0개(굿즈 없음 안내).
- 폴백(분류 실패/타임아웃, §6)은 `eco_points=0, recyclable=false` → 사탕 0개로 안전 처리.

---

## 5. 에러 코드

| 코드 | 의미 | 발생 측 |
|---|---|---|
| `camera_fail` | 카메라 캡처 실패 | Pi |
| `motor_fail` | 서보/벨트 구동 실패 | Pi |
| `belt_jam` | 벨트 걸림 감지 | Pi |
| `result_timeout` | `awaiting_result`에서 iPad 결과 미수신(타임아웃) | Pi |
| `estopped` | 비상 정지됨 | Pi |
| `internal` | 기타 내부 오류 | Pi |

---

## 6. 타임아웃 & 폴백 정책

- **Pi (`awaiting_result`)**: 결과 대기 타이머 기본 **15초**. 초과 시 → `category=other`로 자체 처리(`sorting`)하고 `Status.err=result_timeout`을 1회 실어 보낸 뒤 `idle` 복귀. (참여자 앞에서 멈추지 않게 함)
- **iPad**: **분류(Pi `POST /classify/{cycle}`)가 실패/지연**되면 → `category="other"`, `confidence=0`, `raw="error"|"timeout"`로 결과를 전송. 표시용 사진 GET 실패는 분류를 막지 않는다(독립 — 사진만 미표시). **Pi는 어떤 경우에도 결과를 받는다.**
- **BLE 끊김**: iPad 자동 재연결 + 재구독 + Status로 상태 복구. Pi는 진행 중 사이클을 `reset`(끊김 감지 시) 또는 타임아웃으로 정리.
- **앱 레벨 정지 감지**: iPad는 `Status.seq`가 6초 이상 정지하면 "Pi 응답 없음" UI 표시.

---

## 7. 버전 관리
- 호환성 깨지는 변경 시 DeviceInfo의 `proto`를 올린다.
- iPad는 연결 시 `proto`를 확인해 불일치하면 경고하거나 동작을 차단한다.
- 이 문서가 단일 진실 공급원(single source of truth)이다.

### 7.1 동결(freeze) 상태
- **proto 1 = 동결 기준선.** Pi 레퍼런스 구현(`pi/`)이 모든 특성·상태·폴백 경로를 실제로 구동·검증했고(pytest 51, 통합/스모크 통과), codex 교차리뷰를 반영해 안정화됨.
- Python 미러: `pi/src/trash_sorter/protocol.py` (검증됨). Swift 미러: `ios/.../Protocol.swift` (이 기준선에 맞춰 구현).
- 이후 변경은 양쪽 미러 + 본 문서를 **동시에** 갱신하고 `proto`를 올린다.
