"""런타임 설정값. 모두 환경변수(``TRASH_*``)로 override 가능.

GPIO 핀·서보 구동·타이밍·임계값은 현장 튜닝 대상이라 한 곳에 모은다.
docs/protocol.md §2.5(물리 제어), §6(타임아웃)와 연동.

**런타임 튜닝(가변)**: 서보·벨트·비전·타이밍·디스플레이 sub-config는 ``frozen`` 이 아니다 —
``config_manager.ConfigManager`` 가 iPad의 ``PUT /config`` 요청에 따라 **공유 인스턴스를
in-place 변경**하면, 매 동작마다 ``self._s.<section>.<attr>`` 를 live로 읽는 소비자(오케스트레이터·
서보·벨트)가 재시작 없이 즉시 반영한다(HOT). 변경 경로는 ConfigManager(화이트리스트 §8.3)뿐.
핀·해상도 등 생성 시 캡처되는 값(REINIT)은 노출하지 않는다. docs/protocol.md §8.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .protocol import WasteCategory


def _f(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _i(name: str, default: int) -> int:
    # float-형 문자열("8080.0")도 허용 — int("8080.0")은 ValueError라 startup이 죽는다.
    return int(float(os.environ.get(name, default)))


def _s(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _b(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    return default if raw is None else raw.strip().lower() in ("1", "true", "on", "yes")


def _x(name: str, default: int) -> int:
    # 16진("0x34")·10진("52") 모두 허용 — I2C 주소 등. base=0이 접두어로 진법 추론.
    raw = os.environ.get(name)
    return default if raw is None else int(raw, 0)


# 기본값은 load_settings()/인스턴스 생성 시점에 env를 읽는다(import 시점 고정이 아님)
# → default_factory 사용. 덕분에 런타임/테스트에서 env override가 반영된다.
@dataclass  # 비-frozen: servo.speed/travel_s/rehome_s 런타임 튜닝(/config). 핀·dir은 미노출.
class ServoConfig:
    """게이트 1 + 분기 2 서보. **SER0043(DF9GMS) = 360° 연속회전 서보**(위치제어 불가).

    각도 대신 **저속 구동 + 시간(travel_s)** 으로 기구 하드스톱까지 이동 후 정지한다 —
    최대 이동 위치는 기계식 스톱이 물리적으로 제한하고, 정지 후 위치도 스톱이 유지한다.
    docs/hardware.md "서보" 참조. 전류(5V): 무부하 ~155mA/개, 스톨 ~830mA/개.
    """

    gate_pin: int = field(default_factory=lambda: _i("TRASH_GATE_PIN", 17))
    left_pin: int = field(default_factory=lambda: _i("TRASH_LEFT_PIN", 27))
    right_pin: int = field(default_factory=lambda: _i("TRASH_RIGHT_PIN", 22))

    # 저속 구동 세기(gpiozero Servo.value, 0..1). 낮을수록 느림. 정지는 detach(무신호).
    speed: float = field(default_factory=lambda: _f("TRASH_SERVO_SPEED", 0.3))
    # 한 스톱→반대 스톱 이동 시간(초). 하드스톱까지 충분히 — 현장 캘리브레이션 대상.
    travel_s: float = field(default_factory=lambda: _f("TRASH_SERVO_TRAVEL", 0.8))
    # 'open(방출/분기 열림)' 방향 부호(+1/-1). close는 반대 부호. 기구 장착·배선에 맞게 조정.
    gate_dir: int = field(default_factory=lambda: _i("TRASH_GATE_DIR", 1))
    left_dir: int = field(default_factory=lambda: _i("TRASH_LEFT_DIR", 1))
    right_dir: int = field(default_factory=lambda: _i("TRASH_RIGHT_DIR", 1))
    # 리셋 버튼 '길게-클릭' 재시팅 구동 시간(초). 게이트·분기를 닫힘/중앙 하드스톱으로 다시
    # 안착시키는 시간 — travel_s보다 길게 잡아 드리프트/잼 뒤에도 확실히 재시팅. 3축 동시 구동이라
    # 이 시간 동안 최악 동시 스톨 전류(~2.5A@5V)가 흐른다(docs/hardware.md 전원 주의).
    rehome_s: float = field(default_factory=lambda: _f("TRASH_REHOME_SEC", 1.2))


@dataclass  # 비-frozen: belt.run_seconds 런타임 튜닝(/config). 드라이버·핀·i2c는 미노출(REINIT).
class BeltConfig:
    run_seconds: float = field(default_factory=lambda: _f("TRASH_BELT_SECONDS", 3.0))  # §2.5 T_belt

    # 벨트 드라이버: "gpiozero"(GPIO+L298N류, 현행 기본) | "hiwonder"(I2C 4ch SA8870C).
    # I2C 활성화·보드 배선 후 TRASH_BELT_DRIVER=hiwonder로 전환. docs/hardware.md.
    driver: str = field(default_factory=lambda: _s("TRASH_BELT_DRIVER", "gpiozero"))

    # --- gpiozero(GPIO) 드라이버 핀(BCM) ---
    forward_pin: int = field(default_factory=lambda: _i("TRASH_BELT_FWD_PIN", 23))
    backward_pin: int = field(default_factory=lambda: _i("TRASH_BELT_BWD_PIN", 24))

    # --- Hiwonder 4ch I2C 드라이버(SA8870C) — 폐루프 고정속도(register 0x33) ---
    # 실기기 확정(trash-bjl): 개루프(0x1f)는 이 모터를 못 돌리고 폐루프(0x33)만 강하게 구동된다.
    # ⚠️ 보드 I2C VCC는 반드시 **5V**(보드가 내부 레귤레이터로 3.3V 생성). 3.3V 직결 시 MCU
    # 언더파워 → 구동 중 I2C 버스 행(브라운아웃). 메모리 hiwonder-belt-i2c-rootcause 참조.
    i2c_bus: int = field(default_factory=lambda: _i("TRASH_BELT_I2C_BUS", 1))
    i2c_addr: int = field(default_factory=lambda: _x("TRASH_BELT_I2C_ADDR", 0x34))
    channel: int = field(default_factory=lambda: _i("TRASH_BELT_CHANNEL", 1))  # 모터 포트(M2=idx1)
    # 폐루프 고정속도(-100..100, 부호=방향). 우리 배선은 음수가 정회전(엔코더 위상). 현장 조정.
    speed: int = field(default_factory=lambda: _i("TRASH_BELT_SPEED", -50))
    motor_type: int = field(default_factory=lambda: _i("TRASH_BELT_MOTOR_TYPE", 3))  # 3=JGB37-520
    encoder_polarity: int = field(default_factory=lambda: _i("TRASH_BELT_POLARITY", 0))
    # 폐루프 속도 명령은 보드 watchdog로 ~0.3s 후 감쇠 → 구동 중 이 간격으로 재전송(연속 회전).
    refresh_s: float = field(default_factory=lambda: _f("TRASH_BELT_REFRESH", 0.05))


@dataclass  # 비-frozen: settle/detect_max/motion_threshold 런타임 튜닝(/config). 해상도·awb 미노출.
class VisionConfig:
    # 캡처 해상도. IMX219(Pi Cam v2)는 4:3 센서 → 4:3 풀-FOV 모드(1640×1232)로 화각 손실 방지.
    # 16:9(예 1280×720)는 센서를 크롭해 FOV↓. picamera2_impl이 ScalerCrop=전체로 풀-FOV 강제.
    width: int = field(default_factory=lambda: _i("TRASH_CAM_W", 1640))
    height: int = field(default_factory=lambda: _i("TRASH_CAM_H", 1232))
    jpeg_quality: int = field(default_factory=lambda: _i("TRASH_JPEG_Q", 80))
    motion_threshold: float = field(default_factory=lambda: _f("TRASH_MOTION_THRESH", 0.02))
    # 움직임이 멎은 뒤 '정지' 인정 무동작 지속(초). 이 시간 변이 없으면 촬영(흔들림 방지).
    settle_seconds: float = field(default_factory=lambda: _f("TRASH_SETTLE_SEC", 0.5))
    # 움직임이 계속돼 정지하지 않을 때 강제 촬영까지의 최대 감지시간(초). 무한 대기 방지 안전장치.
    detect_max_seconds: float = field(default_factory=lambda: _f("TRASH_DETECT_MAX", 5.0))
    # 화이트밸런스 수동 게인(red, blue). 둘 다 >0이면 AWB off + 고정. 0(기본)=AWB auto.
    # IR필터 카메라(Pi Cam v2.1/IMX219)는 AWB auto 정확(실측). NoIR/캐스트 시만 고정.
    awb_red_gain: float = field(default_factory=lambda: _f("TRASH_AWB_RED_GAIN", 0.0))
    awb_blue_gain: float = field(default_factory=lambda: _f("TRASH_AWB_BLUE_GAIN", 0.0))


@dataclass(frozen=True)
class NetworkConfig:
    http_port: int = field(default_factory=lambda: _i("TRASH_HTTP_PORT", 8080))
    photo_retention: int = field(default_factory=lambda: _i("TRASH_PHOTO_RETENTION", 20))
    advertised_ip: str = field(default_factory=lambda: _s("TRASH_ADVERTISED_IP", ""))
    # 사진 저장 디렉터리. 빈 값이면 자동(mock=임시디렉터리 / 실기기=/var/tmp/trash-photos).
    # 명시하면 고정 경로로 사진을 시드·검사할 수 있다(E2E·운영 디버깅). factory.build_app 참조.
    photo_dir: str = field(default_factory=lambda: _s("TRASH_PHOTO_DIR", ""))
    # 런타임 튜닝(PUT /config) 영속 파일 경로. 빈 값이면 메모리에만 적용(비영속 — 테스트/개발 기본).
    # 실기기 배포는 쓰기 가능 경로 지정(예 /var/lib/trash-sorter/runtime.json). docs/protocol.md §8.
    config_file: str = field(default_factory=lambda: _s("TRASH_CONFIG_FILE", ""))


@dataclass  # 비-frozen: result_timeout_s/heartbeat_period_s 런타임 튜닝(/config).
class TimingConfig:
    result_timeout_s: float = field(default_factory=lambda: _f("TRASH_RESULT_TIMEOUT", 15.0))  # §6
    heartbeat_period_s: float = field(default_factory=lambda: _f("TRASH_HEARTBEAT", 2.0))


@dataclass(frozen=True)
class ButtonConfig:
    """물리 리셋 버튼(모멘터리 푸시). 짧게=detach-홈 / 길게=타이머 재시팅(서보 홈 복귀).

    배선: 버튼 한쪽 GPIO(pull_up 기준) ↔ 다른 쪽 GND. 눌림=LOW. docs/hardware.md "리셋 버튼".
    디바운스(채터링 방지)·짧게/길게 판정은 PressDetector(순수 로직, clock 주입)가 폴링으로 처리.
    """

    enabled: bool = field(default_factory=lambda: _b("TRASH_RESET_BTN", True))
    pin: int = field(default_factory=lambda: _i("TRASH_RESET_BTN_PIN", 25))  # BCM25(물리22)
    # pull_up=True: 내부 풀업, 버튼=GPIO↔GND, 눌림=LOW(gpiozero 기본). False면 외부 풀다운.
    pull_up: bool = field(default_factory=lambda: _b("TRASH_RESET_BTN_PULLUP", True))
    # debounce_s: 채터링 무시 창(초). long_press_s: 짧게/길게 경계(초).
    debounce_s: float = field(default_factory=lambda: _f("TRASH_RESET_BTN_DEBOUNCE", 0.04))
    long_press_s: float = field(default_factory=lambda: _f("TRASH_RESET_BTN_LONG", 0.8))


@dataclass  # 비-frozen: min_interval_s 런타임 튜닝(/config). enabled·i2c·controller는 미노출.
class DisplayConfig:
    """상태 표시용 I2C OLED(YWROBOT 12864 = 128×64, SSD1306/SH1106). docs/hardware.md "상태 OLED".

    YWROBOT 0.96" 128×64는 보통 SSD1306(0x3C). 제어칩이 SH1106면 ``controller=sh1106``(2px 오프셋
    보정). i2cdetect로 주소 확인. 없거나 I2C 미활성이면 factory가 graceful fallback(표시 없이 진행).
    """

    enabled: bool = field(default_factory=lambda: _b("TRASH_OLED", True))
    i2c_bus: int = field(default_factory=lambda: _i("TRASH_OLED_I2C_BUS", 1))
    i2c_addr: int = field(default_factory=lambda: _x("TRASH_OLED_I2C_ADDR", 0x3C))
    controller: str = field(default_factory=lambda: _s("TRASH_OLED_CONTROLLER", "ssd1306"))
    width: int = field(default_factory=lambda: _i("TRASH_OLED_WIDTH", 128))
    height: int = field(default_factory=lambda: _i("TRASH_OLED_HEIGHT", 64))
    rotate: int = field(default_factory=lambda: _i("TRASH_OLED_ROTATE", 0))  # luma 0..3(×90°)
    # 최소 갱신 간격(초). I2C 트래픽 보호 + 스피너 애니메이션 주기. 상태 변화는 즉시 그린다.
    min_interval_s: float = field(default_factory=lambda: _f("TRASH_OLED_MIN_INTERVAL", 0.5))


# pet/can/other → 분기 경로. §2.5 기본 매핑(물리 배치에 맞게 조정).
ROUTE_MAP: dict[WasteCategory, str] = {
    WasteCategory.PET: "left",     # 분기서보 좌 열림
    WasteCategory.CAN: "right",    # 분기서보 우 열림
    WasteCategory.OTHER: "center",  # 좌·우 모두 닫힘
}


@dataclass  # 비-frozen: sub-config가 가변(런타임 튜닝)이라 frozen은 의미가 없고 __hash__만 깨진다.
class Settings:
    fw_version: str = "0.1.0"
    device_name: str = field(default_factory=lambda: _s("TRASH_DEVICE_NAME", "sorter-01"))
    servo: ServoConfig = field(default_factory=ServoConfig)
    belt: BeltConfig = field(default_factory=BeltConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    timing: TimingConfig = field(default_factory=TimingConfig)
    button: ButtonConfig = field(default_factory=ButtonConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)


def load_settings() -> Settings:
    return Settings()
