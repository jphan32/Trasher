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
| 로직 GND(공통) | GND | 6·9·14·20·25·30·34·39 | — | **외부 전원 GND와 공통 필수** |

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
- 소프트 PWM 지터는 **pigpio**(하드웨어 타이밍) 권장 — [`pi-setup.md`](pi-setup.md) §6.

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

### 전원 주의
- 서보·모터는 Pi 5V 레일에서 직접 빼지 말 것(순간 전류로 Pi 리셋/언더볼트).
- 외부 전원과 Pi는 **GND 공통** 연결.
- **서보 전원(5V) 용량** — SER0043 ×3: idle≈0(detach) / 무부하 3×~155mA≈0.47A / **최악(동시 스톨) 3×~0.83A≈2.5A**. inrush 감안 **5V ≥3A(권장 4–5A)**, Pi 전용 PSU와 분리.

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
4. **벨트 시간 보정**: 투입물이 분리수거함까지 이동하는 데 충분한 `TRASH_BELT_SECONDS` 설정.
5. **비전 임계값 보정**: 캡처 프레임을 `.npy`로 저장 후
   `uv run trash-sorter --tune <frames_dir>` → 제안 `TRASH_MOTION_THRESH` 참고.
6. **무하드웨어 리허설**: `uv run trash-sorter --simulate`로 전 사이클 로그 점검(기구 연결 전).

## 참고
- **OS 설치·패키지·설정 전체 절차: [`pi-setup.md`](pi-setup.md)** (Raspberry Pi 4B 셋업 가이드)
- 핀/서보/시간 기본값: `pi/src/trash_sorter/config.py`
- 물리 시퀀스(홀드→분기→방출→벨트→복귀): `docs/protocol.md` §2.5
- env 예시: `pi/deploy/trash-sorter.env.example`
