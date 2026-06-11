"""런타임 설정값. 모두 환경변수(``TRASH_*``)로 override 가능.

GPIO 핀·서보 구동·타이밍·임계값은 현장 튜닝 대상이라 한 곳에 모은다.
docs/protocol.md §2.5(물리 제어), §6(타임아웃)와 연동.
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
@dataclass(frozen=True)
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


@dataclass(frozen=True)
class BeltConfig:
    run_seconds: float = field(default_factory=lambda: _f("TRASH_BELT_SECONDS", 3.0))  # §2.5 T_belt

    # 벨트 드라이버: "gpiozero"(GPIO+L298N류, 현행 기본) | "hiwonder"(I2C 4ch SA8870C).
    # I2C 활성화·보드 배선 후 TRASH_BELT_DRIVER=hiwonder로 전환. docs/hardware.md.
    driver: str = field(default_factory=lambda: _s("TRASH_BELT_DRIVER", "gpiozero"))

    # --- gpiozero(GPIO) 드라이버 핀(BCM) ---
    forward_pin: int = field(default_factory=lambda: _i("TRASH_BELT_FWD_PIN", 23))
    backward_pin: int = field(default_factory=lambda: _i("TRASH_BELT_BWD_PIN", 24))

    # --- Hiwonder I2C 드라이버(개루프 PWM, register 0x1f) ---
    # 시간 기반 벨트라 폐루프(0x33)·엔코더 PPR 불필요 — 개루프 PWM으로 충분.
    i2c_bus: int = field(default_factory=lambda: _i("TRASH_BELT_I2C_BUS", 1))
    i2c_addr: int = field(default_factory=lambda: _x("TRASH_BELT_I2C_ADDR", 0x34))
    pwm: int = field(default_factory=lambda: _i("TRASH_BELT_PWM", 60))  # 개루프 세기 0..100
    ch_a: int = field(default_factory=lambda: _i("TRASH_BELT_CH_A", 0))  # 보드 채널 인덱스 0..3
    ch_b: int = field(default_factory=lambda: _i("TRASH_BELT_CH_B", 1))
    # 미러 장착(서로 반대 방향) 2모터 → 한쪽 부호를 뒤집어 같은 선속도 방향으로. 배선에 맞게 조정.
    invert_a: bool = field(default_factory=lambda: _b("TRASH_BELT_INVERT_A", False))
    invert_b: bool = field(default_factory=lambda: _b("TRASH_BELT_INVERT_B", True))


@dataclass(frozen=True)
class VisionConfig:
    width: int = field(default_factory=lambda: _i("TRASH_CAM_W", 1280))
    height: int = field(default_factory=lambda: _i("TRASH_CAM_H", 720))
    jpeg_quality: int = field(default_factory=lambda: _i("TRASH_JPEG_Q", 80))
    motion_threshold: float = field(default_factory=lambda: _f("TRASH_MOTION_THRESH", 0.02))
    settle_seconds: float = field(default_factory=lambda: _f("TRASH_SETTLE_SEC", 0.5))


@dataclass(frozen=True)
class NetworkConfig:
    http_port: int = field(default_factory=lambda: _i("TRASH_HTTP_PORT", 8080))
    photo_retention: int = field(default_factory=lambda: _i("TRASH_PHOTO_RETENTION", 20))
    advertised_ip: str = field(default_factory=lambda: _s("TRASH_ADVERTISED_IP", ""))
    # 사진 저장 디렉터리. 빈 값이면 자동(mock=임시디렉터리 / 실기기=/var/tmp/trash-photos).
    # 명시하면 고정 경로로 사진을 시드·검사할 수 있다(E2E·운영 디버깅). factory.build_app 참조.
    photo_dir: str = field(default_factory=lambda: _s("TRASH_PHOTO_DIR", ""))


@dataclass(frozen=True)
class TimingConfig:
    result_timeout_s: float = field(default_factory=lambda: _f("TRASH_RESULT_TIMEOUT", 15.0))  # §6
    heartbeat_period_s: float = field(default_factory=lambda: _f("TRASH_HEARTBEAT", 2.0))


# pet/can/other → 분기 경로. §2.5 기본 매핑(물리 배치에 맞게 조정).
ROUTE_MAP: dict[WasteCategory, str] = {
    WasteCategory.PET: "left",     # 분기서보 좌 열림
    WasteCategory.CAN: "right",    # 분기서보 우 열림
    WasteCategory.OTHER: "center",  # 좌·우 모두 닫힘
}


@dataclass(frozen=True)
class Settings:
    fw_version: str = "0.1.0"
    device_name: str = field(default_factory=lambda: _s("TRASH_DEVICE_NAME", "sorter-01"))
    servo: ServoConfig = field(default_factory=ServoConfig)
    belt: BeltConfig = field(default_factory=BeltConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    timing: TimingConfig = field(default_factory=TimingConfig)


def load_settings() -> Settings:
    return Settings()
