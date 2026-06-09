# Raspberry Pi 4B 셋업 가이드

전시 부스용 "AI 쓰레기 자동 분류기"의 Raspberry Pi 4B를 **OS 설치부터 운영까지** 구성하는 전체 절차.
배선·핀맵 상세는 [`hardware.md`](hardware.md), 네트워크 전제는 [`protocol.md`](protocol.md) §"사진 채널",
앱 배포 스크립트는 [`../pi/deploy/`](../pi/deploy/) 참조. GPIO 핀·기본값은 `pi/src/trash_sorter/config.py`가 진실.

> 대상: **Raspberry Pi 4B (2GB+)**, Raspberry Pi OS **64-bit Bookworm**.

---

## 0. 준비물 (BOM 요약)

| # | 항목 | 비고 |
|---|---|---|
| 1 | Raspberry Pi 4B (2GB↑) + 방열판 | |
| 2 | microSD 32GB↑ (A1/A2) | OS |
| 3 | **Pi 전용 PSU** 5V/3A USB-C 공식 | Pi 단독 급전 |
| 4 | Pi Camera (CSI, v2/v3 또는 호환) + CSI 리본 | picamera2 |
| 5 | 서보 ×3 (게이트1 + 분기 좌/우) | SG90/MG90 등 |
| 6 | DC 기어모터 ×1 + **모터드라이버**(L298N/DRV8871) | 컨베이어 |
| 7 | **서보·모터 전용 전원** 5–6V (서보), 5–12V(모터) | Pi 5V 레일과 분리 |
| 8 | 점퍼선, 공통 GND 배선 | |

⚠️ **서보·모터는 Pi 5V 레일에서 직접 급전하지 말 것** — 순간 전류로 Pi 언더볼트/리셋. 외부 전원 사용 + **Pi와 GND 공통**.

---

## 1. 하드웨어 구성도

```
                ┌──────────────────────────────┐
   인터넷 ◄──── │  WiFi 라우터(인터넷 WAN)        │
                └──────┬─────────────────┬───────┘
                       │ WiFi            │ WiFi
                  ┌────┴─────┐      ┌────┴──────┐
                  │  iPad     │      │ Raspberry │
                  │ (Central) │◄────►│  Pi 4B    │   BLE(제어) + LAN HTTP(사진/분류)
                  └───────────┘      └────┬──────┘
                                          │ GPIO / CSI
        ┌──────────────┬──────────────┬───┴────────┬───────────────┐
        │              │              │            │               │
   게이트 서보    분기 좌 서보    분기 우 서보   모터드라이버      Pi 카메라(CSI)
   GPIO17         GPIO27         GPIO22       IN1=GPIO23
                                              IN2=GPIO24 ── DC 모터(벨트)
        │              │              │            │
        └──────────────┴──────┬───────┴────────────┘
                    서보 5–6V 외부전원 / 모터 5–12V 외부전원
                    (각 V+ ← 외부, GND ← 외부 ── Pi GND 공통)
```

물리 흐름: 투입구 → **게이트(캡처 존 홀드)** → **분기(좌/우/중앙)** → **벨트** → 분리수거함 3구.
동작 시퀀스·분기 매핑은 `protocol.md` §2.5.

---

## 2. 핀맵 (40핀 헤더, BCM)

`config.py` 기본값 기준. 바꾸면 `/etc/trash-sorter.env`의 `TRASH_*`로 override하고 이 표를 갱신.

| 기능 | BCM | 물리 핀 # | 연결 | env override |
|---|---|---|---|---|
| 게이트 서보 PWM | **GPIO17** | 11 | 서보 신호(주황) | `TRASH_GATE_PIN` |
| 분기 좌 서보 PWM | **GPIO27** | 13 | 서보 신호 | `TRASH_LEFT_PIN` |
| 분기 우 서보 PWM | **GPIO22** | 15 | 서보 신호 | `TRASH_RIGHT_PIN` |
| 벨트 모터 IN1(정방향) | **GPIO23** | 16 | 모터드라이버 IN1 | `TRASH_BELT_FWD_PIN` |
| 벨트 모터 IN2(역방향) | **GPIO24** | 18 | 모터드라이버 IN2 | `TRASH_BELT_BWD_PIN` |
| 로직 GND(공통) | GND | 6·9·14·20·25·30·34·39 | **외부전원 GND와 공통** | — |
| 카메라 | CSI 커넥터 | — | 리본 케이블 | — |

- 서보 V+/모터 VM은 **외부 전원**에서, 신호선만 위 GPIO에 연결. Pi GPIO는 3.3V 로직(대부분 서보/드라이버 IN이 수용).
- 서보 각도/벨트 시간 기본: 게이트 닫힘 0°/열림 90°, 분기 닫힘 0°/열림 60°, `T_belt` 3.0s (`TRASH_GATE_OPEN`/`TRASH_DIV_OPEN`/`TRASH_BELT_SECONDS`).
- 배선 상세·전원 주의는 [`hardware.md`](hardware.md).

---

## 3. OS 설치 (Raspberry Pi Imager)

**Raspberry Pi OS (64-bit) — Bookworm**. 헤더리스 운영이므로 **Lite** 권장(iPad가 디스플레이 역할).

1. [Raspberry Pi Imager](https://www.raspberrypi.com/software/)로 microSD에 기록.
2. **고급 옵션(⚙️ / Ctrl+Shift+X)** 에서 헤더리스 설정:
   - 호스트명: `sorter-01` (앱 `device_name` 기본값과 일치)
   - **SSH 활성화**(공개키 권장)
   - WiFi SSID/비밀번호: **부스의 인터넷 라우터**(§9 참조). 국가 `KR`.
   - 사용자: `pi`(systemd 유닛 기본 User) / 비밀번호
   - 로캘: `Asia/Seoul`, 키보드 `kr`(또는 us)
3. SD 삽입 → 부팅 → `ssh pi@sorter-01.local` (또는 IP).

---

## 4. 시스템 패키지 설치 (apt)

```bash
sudo apt update && sudo apt full-upgrade -y

# 카메라 런타임(libcamera C++ 스택 + rpicam 도구). 캡처 엔진 자체는 이 시스템 패키지가 담당.
# (Bookworm/Trixie 현재 패키지명은 rpicam-apps. 구이름 libcamera-apps는 전환 패키지)
sudo apt install -y rpicam-apps

# venv용 카메라 빌드 의존성(-dev) — rpi-libcamera/rpi-kms/python-prctl 소스 빌드에 필요(§10)
sudo apt install -y libcamera-dev libkms++-dev libfmt-dev libdrm-dev \
                    libcap-dev libatlas-base-dev ffmpeg libopenjp2-7

# 서보 PWM 안정화(하드웨어 타이밍) + BLE + 빌드 도구
sudo apt install -y pigpio python3-pigpio \
                    bluez libdbus-1-dev libglib2.0-dev \
                    build-essential git

# uv (Python 환경/의존성 관리)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc   # uv PATH 반영
```

> **picamera2/libcamera 주의 (Python 3.12.10 고정 전제)**: 이 프로젝트의 venv는 **pyenv Python 3.12.10**으로 고정한다. apt `python3-libcamera`는 시스템 Python(3.13) ABI로 컴파일돼 3.12.10 venv에서 `import libcamera`가 실패한다. 따라서 venv에서는 **`rpi-libcamera` + `rpi-kms`** 를 pip로 빌드해 시스템 libcamera에 대한 3.12 바인딩을 얻고 `picamera2`(PyPI)를 동작시킨다(§10, `requirements-pi.txt`에 포함). 위 `-dev` 패키지가 그 빌드 전제다.
>
> 참고: 캡처 엔진(센서·ISP·인코딩)은 어느 경로든 동일한 네이티브 libcamera가 수행하므로 **런타임 카메라 성능 차이는 없다**. 바인딩 패키징만 다르다.

---

## 5. 카메라 활성화

Bookworm은 libcamera 기반으로 카메라 자동 감지. 인식이 안 되면 `/boot/firmware/config.txt` 확인:

```ini
camera_auto_detect=1     # 기본 활성. v3/특정 모듈은 dtoverlay 명시가 필요할 수 있음
# 예) IMX708(v3): dtoverlay=imx708
```

확인:

```bash
libcamera-hello --list-cameras      # 카메라 목록
rpicam-still -o /tmp/test.jpg        # 테스트 촬영(Bookworm 명령명: rpicam-*)
```

---

## 6. 서보 PWM 안정화 (pigpio)

소프트웨어 PWM은 서보 지터가 심하다. **pigpio 데몬**으로 하드웨어 타이밍 PWM을 쓴다(gpiozero `PiGPIOFactory`).

```bash
sudo systemctl enable --now pigpiod        # 부팅 시 자동 + 즉시 시작
```

앱이 pigpio 팩토리를 쓰도록 환경변수 설정(§11 env 파일에 추가):

```bash
GPIOZERO_PIN_FACTORY=pigpio
```

> Bookworm gpiozero 기본 팩토리는 `lgpio`로도 동작하지만, 서보 안정성을 위해 pigpio 권장.

---

## 7. Bluetooth / BLE (bless)

```bash
sudo systemctl enable --now bluetooth      # BlueZ
systemctl status bluetooth                 # active 확인
bluetoothctl show                          # 어댑터 확인(Pi 4B 내장 BT)
```

- 앱은 **bless**(BlueZ/dbus)로 GATT Peripheral 광고. `pi` 사용자가 `bluetooth` 그룹에 있어야 함(§8).
- 외장 BT 동글 없이 Pi 4B 내장 사용. BLE·WiFi 동시 사용 시 §9의 WiFi 절전 끄기 권장(간섭/끊김 완화).

---

## 8. 사용자 권한 (그룹)

`pi` 사용자를 하드웨어 그룹에 추가(로그아웃/재부팅 후 반영):

```bash
sudo usermod -aG gpio,video,bluetooth,dialout,i2c,spi pi
```

- `gpio`: 서보/모터 GPIO, `video`: 카메라, `bluetooth`: BLE, `dialout`: 시리얼(필요 시).

---

## 9. 네트워크 설정

`protocol.md` 전제: **iPad·Pi 모두 인터넷 되는 동일 WiFi 라우터의 클라이언트**(Pi-as-AP 아님). iPad↔Pi는 LAN, Gemini 호출은 Pi가 인터넷으로.

```bash
# WiFi 연결(Imager에서 설정했으면 생략). NetworkManager(Bookworm):
sudo nmcli device wifi connect "<SSID>" password "<PW>"
hostname -I                                 # Pi IP 확인(BLE DeviceInfo로도 광고됨)
```

설정/확인 항목:
- **라우터 인터넷(WAN) 보장** — 불안하면 인터넷 공급 전용 휴대용 라우터 지참.
- **DHCP 예약(고정 임대)**: 라우터에서 Pi MAC에 고정 IP. (보조: mDNS `sorter-01.local`)
- ⚠️ 라우터 **AP/Client Isolation OFF**, iPad·Pi **같은 서브넷**.
- **WiFi 절전 끄기**(BLE/WiFi 안정):
  ```bash
  sudo iw wlan0 set power_save off
  # 영구화: /etc/NetworkManager/conf.d/wifi-powersave.conf 에 [connection] wifi.powersave = 2
  ```
- **방화벽**: 사용 시 LAN에서 HTTP 포트 `8080` 허용(`TRASH_HTTP_PORT`).
- **인터넷 도달 확인**(Gemini):
  ```bash
  curl -sS -o /dev/null -w "%{http_code}\n" https://generativelanguage.googleapis.com
  ```

---

## 10. 앱 설치 (코드 + 의존성)

저장소를 Pi에 복사(git clone 또는 scp) 후, 배포 스크립트로 설치:

먼저 **§4의 apt `-dev` 패키지가 설치돼 있어야 한다**(rpi-libcamera/rpi-kms/python-prctl 빌드 전제).

```bash
git clone <repo-url> ~/trash && cd ~/trash
cd pi

# venv는 pyenv Python 3.12.10으로 고정(시스템 3.13 아님). pyenv에 3.12.10이 없으면:
#   pyenv install 3.12.10
uv venv --python 3.12.10                  # isolated venv (--system-site-packages 사용 안 함)
uv sync                                   # 크로스플랫폼 + dev 도구
uv pip install -r requirements-pi.txt     # picamera2 + rpi-libcamera/rpi-kms + gpiozero/bless/opencv
                                          #   ↳ rpi-libcamera/rpi-kms 컴파일은 Pi 4에서 3분+ 소요

# 카메라 바인딩 검증(실패하면 §4 -dev 패키지 누락 의심)
uv run python -c "import picamera2, libcamera; print('camera OK')"

# 무하드웨어 점검(설치 검증)
uv run trash-sorter --simulate            # 전 사이클 로그
```

또는 **systemd 자동 설치**(권장, 부스 무인 기동):

```bash
sudo bash pi/deploy/install.sh            # /opt/trash-sorter 복사 + uv sync + 서비스 등록·시작
```

> `install.sh`는 `uv sync` → `uv pip install -r requirements-pi.txt`를 수행한다(rpi-libcamera/rpi-kms 포함). 따라서 실행 전 **§4의 `-dev` 패키지**가 깔려 있어야 빌드가 성공한다. venv Python을 3.12.10으로 고정하려면 pi 디렉터리에 `.python-version`(`3.12.10`)을 두거나, Pi에서 `uv venv --python 3.12.10`으로 venv를 먼저 구성한 뒤 서비스만 등록한다. (`--system-site-packages`는 사용하지 않는다 — 3.12.10 ABI와 apt 3.13 패키지가 호환되지 않기 때문.)

---

## 11. 환경설정 (`/etc/trash-sorter.env`)

systemd 유닛이 읽는 env 파일. 예시 복사 후 편집(`pi/deploy/trash-sorter.env.example`):

```bash
sudo cp pi/deploy/trash-sorter.env.example /etc/trash-sorter.env
sudo nano /etc/trash-sorter.env
```

핵심 항목:

```ini
# 서보 안정화(§6)
GPIOZERO_PIN_FACTORY=pigpio

# 네트워크
TRASH_ADVERTISED_IP=          # 빈 값=자동감지(DHCP 예약 시 비워도 됨)
TRASH_HTTP_PORT=8080
TRASH_DEVICE_NAME=sorter-01

# GPIO 핀(§2와 일치) / 서보각 / 벨트시간 — 캘리브레이션 후 조정
TRASH_GATE_PIN=17
TRASH_LEFT_PIN=27
TRASH_RIGHT_PIN=22
TRASH_BELT_FWD_PIN=23
TRASH_BELT_BWD_PIN=24
TRASH_BELT_SECONDS=3.0

# 비전 임계값 — --tune으로 보정
TRASH_MOTION_THRESH=0.02
TRASH_SETTLE_SEC=0.5

# Gemini 분류(/classify) — SA 키 경로(없으면 Mock 분류기로 동작)
TRASH_GEMINI_CREDENTIALS=/opt/trash-sorter/secret/gemini-api-key.json
TRASH_GEMINI_MODEL=gemini-3.5-flash
```

### 비밀키 배치 (Gemini)

```bash
sudo mkdir -p /opt/trash-sorter/secret
sudo cp gemini-api-key.json /opt/trash-sorter/secret/
sudo chown -R pi:pi /opt/trash-sorter/secret
sudo chmod 600 /opt/trash-sorter/secret/gemini-api-key.json
```

> 키는 **절대 git에 커밋 금지**(`secret/`는 gitignore). 키가 없으면 분류는 `MockClassifier`로 폴백.

---

## 12. 캘리브레이션

1. **서보 각도**: 운영자 정비 화면(iPad, 좌상단 3초 길게)에서 `sort pet/can/other`·`belt fwd/stop`로 개별 구동 → `TRASH_GATE_OPEN/CLOSED`, `TRASH_DIV_OPEN/CLOSED` 조정.
2. **벨트 시간**: 투입물이 분리수거함까지 이동하는 시간으로 `TRASH_BELT_SECONDS` 설정.
3. **비전 임계값**: 캡처 프레임을 `.npy`로 저장 후
   ```bash
   uv run trash-sorter --tune <frames_dir>      # 제안 TRASH_MOTION_THRESH 출력
   ```
4. **분기 매핑**: 분리수거함 물리 배치가 다르면 `config.ROUTE_MAP`(코드) 수정.

---

## 13. 검증 & 운영

```bash
# 서비스 상태/로그
systemctl status trash-sorter
journalctl -u trash-sorter -f

# 분류 엔드포인트 수동 확인(사진이 store에 있을 때)
curl -X POST http://localhost:8080/classify/1

# 무하드웨어 점검
uv run trash-sorter --simulate
```

- **자동 재시작/부팅 기동**: systemd `Restart=always` + `enable`(install.sh가 설정).
- iPad 앱에서 BLE 연결(서비스 UUID 스캔) → DeviceInfo로 Pi IP 수신 → 사진 GET + `/classify` 호출.

---

## 14. 설정 체크리스트

- [ ] Pi OS 64-bit Bookworm Lite, 호스트명 `sorter-01`, SSH/WiFi/로캘
- [ ] `rpicam-still` 카메라 동작 + venv에서 `import picamera2, libcamera` 성공(§4 -dev + rpi-libcamera/rpi-kms)
- [ ] `pigpiod` enable + `GPIOZERO_PIN_FACTORY=pigpio`
- [ ] `bluetooth` 서비스 active, `pi`가 `bluetooth` 그룹
- [ ] `pi` ∈ `gpio,video,bluetooth,dialout`
- [ ] WiFi = 인터넷 라우터, DHCP 예약, AP격리 OFF, **WiFi 절전 off**
- [ ] 인터넷 도달(Gemini) 확인, 포트 8080 LAN 허용
- [ ] 서보 3·모터1 **외부 전원** + Pi와 **공통 GND** (Pi 5V 직급전 금지)
- [ ] 앱 설치(uv venv `--python 3.12.10` + requirements-pi[rpi-libcamera/rpi-kms 포함]) / `install.sh`
- [ ] `/etc/trash-sorter.env` (핀·임계값·`TRASH_GEMINI_CREDENTIALS`)
- [ ] 비밀키 `/opt/trash-sorter/secret/` 배치(600), git 미커밋
- [ ] 캘리브레이션(서보각/벨트시간/임계값) 완료
- [ ] `systemctl status trash-sorter` active, journald 로그 정상
- [ ] iPad BLE 연결 + 사진/분류 1사이클 검증
