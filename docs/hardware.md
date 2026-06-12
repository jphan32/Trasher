# 하드웨어 레퍼런스 (배선·핀맵·BOM·조립)

Raspberry Pi 물리 구성 레퍼런스. GPIO 핀은 `pi/src/trash_sorter/config.py`의 기본값과 일치하며,
현장에서 바꾸면 `/etc/trash-sorter.env`(`TRASH_*`)로 override하고 이 문서를 함께 갱신한다.
물리 동작·시퀀스의 정의는 [`protocol.md` §2.5](protocol.md)가 단일 진실.

## 구성 요소

| # | 부품 | 역할 |
|---|---|---|
| 1 | Raspberry Pi 4B (BLE 내장) | 제어·비전·BLE Peripheral·HTTP 사진서버 |
| 2 | picamera2 호환 카메라(CSI) | 변이 감지 + 사진 촬영 |
| 3 | 게이트 서보 ×1 — **SER0043**(DF9GMS, 360° 연속회전, 9g, 4.8–6V) | 투입물 정위치 홀드(닫힘) / 방출(열림). 하드스톱+시간제어 |
| 4 | 분기 서보 ×2 (좌/우) — **SER0043** | 경로 분기: 좌 열림=좌, 우 열림=우, 둘 다 닫힘=중앙 |
| 5 | 벨트 모터 — Wheeltec MG310P20 ×2 + 드라이버(Hiwonder 4ch I2C SA8870C, 또는 L298N류) | 컨베이어 구동(시간 기반). 전력상 2채널. **hiwonder I2C는 Pi 직결**(공식 RPi 키트 사례, smbus2·0x34) |
| 6 | 외부 전원 — 서보 **4.8–6V**(5V ≥3A) + 모터 **7.4V**(MG310P20 7.4V판, 보드 VM 5–15V·≥5A) | 서보·모터 전류(Pi 5V 레일과 분리, **공통 GND 필수**) |
| 7 | **물리 리셋 버튼 ×1** (모멘터리 푸시, NO) | 서보 홈 복귀. 짧게=detach-홈 / 길게=타이머 재시팅. GPIO↔버튼↔GND(내부 풀업) |
| 8 | **상태 OLED — YWROBOT 12864 I2C**(0.96" 128×64, SSD1306, 0x3C, VCC 3.3–5V) | Pi 동작 상태 표시(운영자용). I2C1(GPIO2/3) — Hiwonder 벨트와 버스 공유 가능(주소 0x3C≠0x34) |

## GPIO 핀맵 (BCM, config.py 기본값)

| 신호 | BCM 핀 | 물리 핀# | config / env | 비고 |
|---|---|---|---|---|
| 게이트 서보 PWM | **GPIO17** | 11 | `gate_pin` / `TRASH_GATE_PIN` | gpiozero `Servo`(연속회전, SER0043) |
| 분기 서보 좌 PWM | **GPIO27** | 13 | `left_pin` / `TRASH_LEFT_PIN` | |
| 분기 서보 우 PWM | **GPIO22** | 15 | `right_pin` / `TRASH_RIGHT_PIN` | |
| 벨트 IN1 *(driver=gpiozero)* | **GPIO23** | 16 | `forward_pin` / `TRASH_BELT_FWD_PIN` | 모터드라이버 IN1 |
| 벨트 IN2 *(driver=gpiozero)* | **GPIO24** | 18 | `backward_pin` / `TRASH_BELT_BWD_PIN` | 모터드라이버 IN2 |
| 벨트 I2C SDA *(driver=hiwonder)* | **GPIO2** | 3 | `i2c_addr` / `TRASH_BELT_I2C_ADDR` | I2C1 SDA, 보드 기본 `0x34` |
| 벨트 I2C SCL *(driver=hiwonder)* | **GPIO3** | 5 | `i2c_bus` / `TRASH_BELT_I2C_BUS` | I2C1 SCL, bus `1` |
| **리셋 버튼** | **GPIO25** | 22 | `pin` / `TRASH_RESET_BTN_PIN` | 모멘터리 NO, 반대쪽 GND. 내부 풀업(눌림=LOW) |
| **OLED I2C SDA** | **GPIO2** | 3 | `i2c_addr` / `TRASH_OLED_I2C_ADDR` | I2C1 SDA, `0x3C`. SDA는 GPIO2 공용(버스) |
| **OLED I2C SCL** | **GPIO3** | 5 | `i2c_bus` / `TRASH_OLED_I2C_BUS` | I2C1 SCL, bus `1`. SCL는 GPIO3 공용(버스) |
| 로직 GND(공통) | GND | 6·9·14·20·25·30·34·39 | — | **외부 전원 GND와 공통 필수** |
| OLED VCC(3.3V) | 3V3 | 1·17 | — | OLED 전원(~20mA, Pi 3.3V 레일) |

> 서보(연속회전) 기본값: 저속 `speed` 0.3, 이동시간 `travel_s` 0.8s, 방향 `*_dir` ±1 — 하드스톱까지 구동 후 정지. 벨트 `T_belt` 3.0s.
> (`TRASH_SERVO_SPEED`/`TRASH_SERVO_TRAVEL`, `TRASH_GATE_DIR`/`TRASH_LEFT_DIR`/`TRASH_RIGHT_DIR`, `TRASH_BELT_SECONDS`로 보정.)
> 벨트 드라이버는 `TRASH_BELT_DRIVER`로 선택(`gpiozero` 현행 기본 | `hiwonder` I2C). 둘은 배타적.

## 배선

### 서보 ×3 (게이트·분기 좌·분기 우) — SER0043(DF9GMS, 360° 연속회전)
```
서보 신호(주황) ── GPIO17 / 27 / 22
서보 V+(빨강)   ── 4.8–6V 외부 전원 +    (Pi 5V로 직접 X — 전류 부족/리셋)
서보 GND(갈색)  ── 외부 전원 GND ── Pi GND   (공통 GND 필수)
```
- **연속회전 서보**(각도 유지 불가) → 저속(`speed`)으로 `travel_s` 동안 목표 방향 구동해 **기구 하드스톱**까지 보낸 뒤 신호를 끊어(detach) 정지. 최대 이동 위치는 스톱이 물리적으로 제한·유지. **각 축 개·폐 양끝 하드스톱 필수**.
- 정지=detach라 idle 전류 ≈ 0. 동작 중 무부하 ~155mA/개, **스톨 ~830mA/개**(@5V).
- 서보 PWM은 gpiozero **lgpio** 기본 팩토리로 동작(Trixie엔 pigpio 데몬 없음). 연속회전+하드스톱이라 소프트 PWM 지터 영향은 미미 — [`pi-setup.md`](pi-setup.md) §6.

### 벨트 모터

벨트는 **시간 기반**(T_belt초 구동 후 정지, §2.5)이라 폐루프가 필요 없다 → 개루프로 충분.
드라이버는 `TRASH_BELT_DRIVER`로 선택한다.

**(A) Hiwonder 4채널 엔코더 모터 드라이버 (SA8870C, I2C) — 계획**

> 사양: 칩 **SA8870C**, VM 5–15V, 출력 VM/5V(1A)/3.3V, 입력 역결선 보호, 채널 2A·피크 2.5A.

모터 = Wheeltec **MG310P20** ×2. 전력 한계로 **2채널만** 사용. 두 모터는 벨트 구동부 한쪽에
**서로 반대 방향**으로 장착되므로, 한 채널 부호를 뒤집어(`TRASH_BELT_INVERT_B`, 기본 true)
같은 선속도 방향을 만든다. 보드 자체 MCU가 엔코더·폐루프를 처리하므로 Pi는 I2C로 PWM만 쓴다.
```
Pi GPIO2(SDA) ── 보드 SDA      Pi GPIO3(SCL) ── 보드 SCL      Pi GND ── 보드 GND (공통 필수)
보드 VM(모터전원) ── 독립 7.4V 전원(2S, ≥5A)        보드 채널0/1 OUT ── MG310P20(7.4V) ×2
```
- **전압 인가(단일 VM)**: 모터 전원만 보드 VM에 인가 → **온보드 레귤레이터**가 VM에서 5V(1A)/3.3V를 만들어 보드 MCU·엔코더를 자체 구동(**별도 로직 전원 불필요**). 입력 **역결선 보호** 있음. 모터 전원은 Pi·서보와 **독립**(스톨/기동 전류가 Pi로 흐르면 브라운아웃).
- **I2C 결선 — Pi 직결(레벨시프터 불필요), 사례로 확정**:
  - **근거**: Hiwonder **공식 RPi 로봇 키트**(Mecanum/Ackerman 섀시 등)가 이 보드를 Raspberry Pi와 **I2C 직결**로 구동 — 공식 튜토리얼이 `smbus2` + 주소 **`0x34`** 로 제어하며 **레벨시프터를 쓰지 않는다**. Pi5 사용자도 내장 1.8kΩ(3.3V) 풀업으로 직결.
  - 결선: 보드 **SDA─Pi GPIO2(SDA, 3번핀) / SCL─Pi GPIO3(SCL, 5번핀) / GND─GND** 3선. **Pi 내장 1.8kΩ(3.3V) 풀업 사용**(외부 풀업 불필요).
  - 보드 IIC **`5V` 핀은 Pi에 연결 금지**(전원용 — 사양/Q&A상 출력/입력 표기 상충하나 Pi 신호선과 무관). Pi·보드 전원은 별도(VM 7.4V), GND만 공통.
  - ⚠️ 일반 원칙: Pi GPIO는 3.3V·5V 비관용. 보드 변종이 SDA/SCL을 5V로 풀업할 가능성에 대비해 **첫 배선 시 SDA/SCL 아이들 ≤3.3V 1회 측정**하면 100% 안전(측정값 5V면 그때만 레벨시프터).
- **풀업**: RP4B GPIO2/3 내장 1.8kΩ로 단일 보드·짧은 케이블이면 보통 충분(외부 추가 시 4.7kΩ↑, 과풀업 주의).
- **공급 용량**: 채널당 정격 2A·피크 2.5A → 2채널 사용 시 **7.4V ≥5A** 권장.
- 제어: 개루프 고정 PWM(register `0x1f`, 채널별 -100..100). 폐루프(`0x33`)·엔코더 PPR(Hall/GMR)은 belt에 불필요.
- **선결(현재 미충족)**: I2C 활성화(`dtparam=i2c_arm=on` + 재부팅) → `sudo apt install i2c-tools` →
  `i2cdetect -y 1`로 주소 확인(기본 가정 `0x34`). 절차는 [`pi-setup.md`](pi-setup.md).
- env: `TRASH_BELT_DRIVER=hiwonder`, `TRASH_BELT_I2C_ADDR/BUS`, `TRASH_BELT_CH_A/B`, `TRASH_BELT_PWM`, `TRASH_BELT_INVERT_A/B`.
- 프로토콜(0x1f 4채널 블록 형식)은 공식 자료로 확정: <https://www.hiwonder.com/products/4-channel-encoder-motor-driver>

**(B) GPIO + 모터드라이버 (L298N / DRV8871류) — 현행 기본**
```
Pi GPIO23 ── 드라이버 IN1   Pi GPIO24 ── 드라이버 IN2   OUT1/2 ── DC 모터
드라이버 VM ── 7.4V 외부 전원(L298N ~2V 강하로 모터 실효전압↓ — Hiwonder 권장)   드라이버 GND ── Pi GND(공통)
```
gpiozero `Motor(forward=23, backward=24)` — 정방향만 사용(시간 기반 완료).

### 카메라
CSI 리본을 Pi 카메라 포트에 연결. picamera2로 인식(실기기). 캡처 존(게이트 위치) 위를 향하게 고정.
- **화각**: IMX219=4:3 센서 → 4:3 풀해상도(1640×1232) + ScalerCrop 전체로 캡처(16:9는 FOV 협소·줌인).
- **화이트밸런스**: **IR-cut 필터 있는 카메라(Pi Cam v2.1/IMX219)는 AWB auto가 정확**(흰색=흰색, 실측)
  → 기본 `TRASH_AWB_RED_GAIN=0`/`BLUE=0`(AWB auto). ⚠️ **NoIR(필터 없는) 카메라는 흰색이 분홍·적색으로
  틀어진다**(IR 오염, 소프트로 완전 보정 불가) → **IR 필터 있는 일반 카메라 사용**. 색 캐스트 잔존 시에만
  수동 ColourGains 고정(흰 A4를 화면 채워 중앙 R≈G≈B 되는 red/blue 게인).

### 리셋 버튼 (서보 홈 복귀, 모멘터리 푸시)
```
버튼 단자 A ── GPIO25 (물리 22핀)
버튼 단자 B ── GND     (Pi 어느 GND핀이든)
```
- **모멘터리 NO(normally-open) 푸시버튼 1개**. 한쪽을 GPIO25, 다른 한쪽을 GND에 연결. gpiozero `Button`이 **내부 풀업**을 켜므로(`pull_up=True` 기본) 평상시 HIGH, **눌림=LOW** — 외부 저항 불필요.
- **디바운스(채터링 방지)는 소프트웨어**(`PressDetector`)가 처리(기본 `TRASH_RESET_BTN_DEBOUNCE` 40ms). RC/캐패시터 불필요.
- 동작(연속회전 서보는 위치 피드백이 없어 '홈'은 하드스톱으로만 정의):
  - **짧게 클릭(SHORT)** = *detach-홈*: 서보 구동을 멈추고(무신호) **현재 위치를 홈으로 간주**(손으로 맞춘 위치 고정용, 물리 이동 없음).
  - **길게 클릭(LONG, ≥`TRASH_RESET_BTN_LONG` 0.8s)** = *타이머 재시팅*: 게이트·분기를 닫힘/중앙 하드스톱 방향으로 `TRASH_REHOME_SEC`(1.2s) 동안 동시 구동해 **물리적으로 재시팅** 후 정지(드리프트/잼 복구).
  - **항상 동작(오버라이드)**: 분류 사이클·정렬·ERROR·MAINTENANCE 어느 상태든 즉시 개입(진행 정지 → 홈 → idle). E-STOP과는 별개의 정비/캘리브레이션용 물리 버튼.
- ⚠️ **길게(재시팅)는 서보 3축을 동시에 하드스톱으로 구동** → 그 시간 동안 **최악 동시 스톨 ~2.5A(@5V)**. 서보 5V 전원이 ≥3A인지 확인(아래 "전원 주의").

### 상태 OLED (YWROBOT 12864 I2C, 운영자용 동작 표시)
```
OLED VCC ── Pi 3V3 (물리 1 또는 17핀)      OLED GND ── Pi GND
OLED SDA ── GPIO2 (물리 3핀, I2C1 SDA)     OLED SCL ── GPIO3 (물리 5핀, I2C1 SCL)
```
- **YWROBOT "Display 12864" 0.96" 128×64 I2C** — 제어칩 **SSD1306**, 주소 **`0x3C`**(대개). 칩이 **SH1106** 변종이면 `TRASH_OLED_CONTROLLER=sh1106`(2px 오프셋 보정). 라이브러리 `luma.oled`가 둘 다 지원.
- **VCC는 3.3–5V** 모듈(YWROBOT은 보통 둘 다 허용). I2C 신호 안정성을 위해 **Pi 3.3V 레일** 권장(SDA/SCL이 3.3V 로직과 일치, ~20mA라 Pi 3.3V로 충분).
- **I2C1 버스 공유**: Hiwonder 벨트 드라이버(`0x34`)와 **같은 SDA/SCL을 공유**해도 된다(주소가 `0x3C`≠`0x34`로 다름). 두 장치가 GPIO2/3에 병렬로 붙는다(I2C는 멀티드롭 버스). 풀업은 Pi 내장 1.8kΩ로 충분.
- 표시 내용(영문 약어, 128×64): **헤더**=장치명+IP(Pi 식별), **대형**=상태(`READY`/`PAUSED`/`DETECT`/`CAPTURE`/`WAIT AI`/`SORTING`/`ERROR`/`MAINT`)+회전 스피너(살아있음), **하단**=`C<cycle> <결과>` / `BLE ok|--` 또는 오류코드. 참여자 대면 UI는 iPad이고 이 화면은 **운영자 진단용**이라 영문이면 충분(한글 글리프 폰트 불요).
- 선결: **I2C 활성화**(`dtparam=i2c_arm=on` + 재부팅) — [`pi-setup.md`](pi-setup.md) §6.2. 없거나 미배선이면 앱이 graceful fallback(표시 없이 정상 동작).

### 전원 주의
- 서보·모터는 Pi 5V 레일에서 직접 빼지 말 것(순간 전류로 Pi 리셋/언더볼트).
- 외부 전원과 Pi는 **GND 공통** 연결.
- **서보 전원(5V) 용량** — SER0043 ×3: idle≈0(detach) / 무부하 3×~155mA≈0.47A / **최악(동시 스톨) 3×~0.83A≈2.5A**. inrush 감안 **5V ≥3A(권장 4–5A)**, Pi 전용 PSU와 분리. 리셋 버튼 **길게(재시팅)가 3축 동시 구동**으로 이 최악 전류를 의도적으로 만든다 — `TRASH_REHOME_SEC` 동안 지속되므로 용량 확인.

## 분기 매핑 (config `ROUTE_MAP`)

| 카테고리 | 경로 | 서보 상태 |
|---|---|---|
| `pet` (페트) | 좌 | 좌 열림, 우 닫힘 |
| `can` (캔) | 우 | 우 열림, 좌 닫힘 |
| `other` (기타) | 중앙 | 좌·우 모두 닫힘 |

물리 분리수거함 배치를 바꾸면 `config.ROUTE_MAP`(코드)을 그에 맞게 수정한다.

## 조립 / 캘리브레이션 절차

1. **기구 조립**: 투입구 → 게이트(캡처 존) → 분기(좌/우/중앙) → 벨트 → 분리수거함 3구.
2. **카메라 정렬**: 캡처 존이 프레임 중앙에 오도록 고정.
3. **서보(연속회전) 보정**: 양끝 **하드스톱** 설치 후 `TRASH_SERVO_SPEED`(저속)·`TRASH_SERVO_TRAVEL`(스톱 도달 시간)·`TRASH_*_DIR`(개/폐 방향 부호) 조정. 정지 시 스톱에 안착하는지 확인.
   - 수동 점검: 운영자 정비 화면(iPad)에서 `sort pet/can/other`, `belt fwd/stop`으로 개별 구동.
   - **물리 리셋 버튼**: 짧게=현재 위치를 홈으로(detach), 길게=하드스톱 재시팅(`TRASH_REHOME_SEC` 조정). 재시팅이 약하면(스톱 미도달) 시간을 늘리고, 너무 길면(스톨 지속) 줄인다.
4. **벨트 시간 보정**: 투입물이 분리수거함까지 이동하는 데 충분한 `TRASH_BELT_SECONDS` 설정.
5. **비전 임계값 보정**: 캡처 프레임을 `.npy`로 저장 후
   `uv run trash-sorter --tune <frames_dir>` → 제안 `TRASH_MOTION_THRESH` 참고.
6. **무하드웨어 리허설**: `uv run trash-sorter --simulate`로 전 사이클 로그 점검(기구 연결 전).

## 참고
- **OS 설치·패키지·설정 전체 절차: [`pi-setup.md`](pi-setup.md)** (Raspberry Pi 4B 셋업 가이드)
- 핀/서보/시간 기본값: `pi/src/trash_sorter/config.py`
- 물리 시퀀스(홀드→분기→방출→벨트→복귀): `docs/protocol.md` §2.5
- env 예시: `pi/deploy/trash-sorter.env.example`
