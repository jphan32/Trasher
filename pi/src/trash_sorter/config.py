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
    # float-형 문자열("8080.0")도 허용 — int("8080.0")은 ValueError라 startup이 죽는다.
    return int(float(os.environ.get(name, default)))


def _s(name: str, default: str) -> str:
    return os.environ.get(name, default)


# 기본값은 load_settings()/인스턴스 생성 시점에 env를 읽는다(import 시점 고정이 아님)
# → default_factory 사용. 덕분에 런타임/테스트에서 env override가 반영된다.
@dataclass(frozen=True)
class ServoConfig:
    """게이트 1 + 분기 2 서보. 각도는 gpiozero AngularServo 기준(도)."""

    gate_pin: int = field(default_factory=lambda: _i("TRASH_GATE_PIN", 17))
    left_pin: int = field(default_factory=lambda: _i("TRASH_LEFT_PIN", 27))
    right_pin: int = field(default_factory=lambda: _i("TRASH_RIGHT_PIN", 22))

    gate_closed_deg: float = field(default_factory=lambda: _f("TRASH_GATE_CLOSED", 0.0))
    gate_open_deg: float = field(default_factory=lambda: _f("TRASH_GATE_OPEN", 90.0))
    diverter_closed_deg: float = field(default_factory=lambda: _f("TRASH_DIV_CLOSED", 0.0))
    diverter_open_deg: float = field(default_factory=lambda: _f("TRASH_DIV_OPEN", 60.0))


@dataclass(frozen=True)
class BeltConfig:
    forward_pin: int = field(default_factory=lambda: _i("TRASH_BELT_FWD_PIN", 23))
    backward_pin: int = field(default_factory=lambda: _i("TRASH_BELT_BWD_PIN", 24))
    run_seconds: float = field(default_factory=lambda: _f("TRASH_BELT_SECONDS", 3.0))  # §2.5 T_belt


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
