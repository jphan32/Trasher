"""런타임 설정값. 모두 환경변수(``TRASH_*``)로 override 가능.

GPIO 핀·서보 각도·타이밍·임계값은 현장 튜닝 대상이라 한 곳에 모은다.
docs/protocol.md §2.5(물리 제어), §6(타임아웃)와 연동.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .protocol import WasteCategory


def _f(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _i(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _s(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class ServoConfig:
    """게이트 1 + 분기 2 서보. 각도는 gpiozero AngularServo 기준(도)."""

    gate_pin: int = _i("TRASH_GATE_PIN", 17)
    left_pin: int = _i("TRASH_LEFT_PIN", 27)
    right_pin: int = _i("TRASH_RIGHT_PIN", 22)

    gate_closed_deg: float = _f("TRASH_GATE_CLOSED", 0.0)   # 캡처 홀드
    gate_open_deg: float = _f("TRASH_GATE_OPEN", 90.0)      # 방출
    diverter_closed_deg: float = _f("TRASH_DIV_CLOSED", 0.0)
    diverter_open_deg: float = _f("TRASH_DIV_OPEN", 60.0)


@dataclass(frozen=True)
class BeltConfig:
    forward_pin: int = _i("TRASH_BELT_FWD_PIN", 23)
    backward_pin: int = _i("TRASH_BELT_BWD_PIN", 24)
    run_seconds: float = _f("TRASH_BELT_SECONDS", 3.0)      # §2.5 T_belt (시간 기반 완료)


@dataclass(frozen=True)
class VisionConfig:
    width: int = _i("TRASH_CAM_W", 1280)
    height: int = _i("TRASH_CAM_H", 720)
    jpeg_quality: int = _i("TRASH_JPEG_Q", 80)
    motion_threshold: float = _f("TRASH_MOTION_THRESH", 0.02)  # 변화 픽셀 비율
    settle_seconds: float = _f("TRASH_SETTLE_SEC", 0.5)        # 안정화 후 촬영


@dataclass(frozen=True)
class NetworkConfig:
    http_port: int = _i("TRASH_HTTP_PORT", 8080)
    photo_retention: int = _i("TRASH_PHOTO_RETENTION", 20)    # 최근 N장 순환 보관
    advertised_ip: str = _s("TRASH_ADVERTISED_IP", "")        # 빈 값이면 자동 감지


@dataclass(frozen=True)
class TimingConfig:
    result_timeout_s: float = _f("TRASH_RESULT_TIMEOUT", 15.0)  # §6 awaiting_result 타임아웃
    heartbeat_period_s: float = _f("TRASH_HEARTBEAT", 2.0)      # Status notify 주기


# pet/can/other → 분기 경로. §2.5 기본 매핑(물리 배치에 맞게 조정).
ROUTE_MAP: dict[WasteCategory, str] = {
    WasteCategory.PET: "left",     # 분기서보 좌 열림
    WasteCategory.CAN: "right",    # 분기서보 우 열림
    WasteCategory.OTHER: "center",  # 좌·우 모두 닫힘
}


@dataclass(frozen=True)
class Settings:
    fw_version: str = "0.1.0"
    device_name: str = _s("TRASH_DEVICE_NAME", "sorter-01")
    servo: ServoConfig = field(default_factory=ServoConfig)
    belt: BeltConfig = field(default_factory=BeltConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    timing: TimingConfig = field(default_factory=TimingConfig)


def load_settings() -> Settings:
    return Settings()
