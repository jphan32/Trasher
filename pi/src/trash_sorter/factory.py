"""플랫폼 분기 조립. Linux(Pi)=실기기 구현, 그 외=Mock. docs/protocol.md 전반.

macOS/CI에서 import해도 안전하도록 실기기 구현은 **함수 내부에서 지연 import**한다.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .app import Orchestrator
from .ble.base import BleServer
from .config import Settings, load_settings
from .hardware.base import HardwareController
from .protocol import DeviceInfo
from .state import StateMachine
from .vision.base import Camera
from .vision.motion import MotionDetector
from .web.photo_server import PhotoServer, PhotoStore, get_lan_ip


def is_raspberry_pi() -> bool:
    """실제 Raspberry Pi 여부. 임의의 Linux(CI/개발 서버)는 False여야 Mock이 선택된다."""
    model = Path("/proc/device-tree/model")
    try:
        return "raspberry pi" in model.read_text(errors="ignore").lower()
    except OSError:
        return False


def use_mock_default() -> bool:
    """환경변수 override(TRASH_MOCK=1/0) 우선, 없으면 'Pi가 아니면 Mock'."""
    override = os.environ.get("TRASH_MOCK")
    if override is not None:
        return override.strip().lower() in ("1", "true", "on", "yes")
    return not is_raspberry_pi()


@dataclass
class AppContext:
    orchestrator: Orchestrator
    ble: BleServer
    photo_server: PhotoServer
    hardware: HardwareController
    camera: Camera


def _build_hardware(settings: Settings, mock: bool) -> HardwareController:
    if mock:
        from .hardware.mock import MockHardware

        return MockHardware()
    from .hardware.gpiozero_impl import GpiozeroHardware

    return GpiozeroHardware(settings)


def _build_camera(settings: Settings, mock: bool) -> Camera:
    if mock:
        from .vision.mock import MockCamera

        return MockCamera()
    from .vision.picamera2_impl import Picamera2Camera

    return Picamera2Camera(settings)


def _build_ble(settings: Settings, mock: bool) -> BleServer:
    if mock:
        from .ble.mock import MockBleServer

        return MockBleServer()
    from .ble.bless_impl import BlessBleServer

    return BlessBleServer(name=settings.device_name)


def build_app(settings: Settings | None = None, *, mock: bool | None = None) -> AppContext:
    settings = settings or load_settings()
    use_mock = use_mock_default() if mock is None else mock

    photo_dir = tempfile.mkdtemp(prefix="trash-photos-") if use_mock else "/var/tmp/trash-photos"
    store = PhotoStore(photo_dir, retention=settings.network.photo_retention)
    photo_server = PhotoServer(store, port=settings.network.http_port)

    hardware = _build_hardware(settings, use_mock)
    camera = _build_camera(settings, use_mock)
    ble = _build_ble(settings, use_mock)

    orchestrator = Orchestrator(
        settings=settings,
        state=StateMachine(),
        camera=camera,
        motion=MotionDetector(
            threshold=settings.vision.motion_threshold,
        ),
        hardware=hardware,
        ble=ble,
        store=store,
    )

    # DeviceInfo는 HTTP 포트가 정해진 뒤(서버 시작 후) set_device_info로 갱신.
    return AppContext(
        orchestrator=orchestrator,
        ble=ble,
        photo_server=photo_server,
        hardware=hardware,
        camera=camera,
    )


def device_info(settings: Settings, http_port: int) -> DeviceInfo:
    ip = settings.network.advertised_ip or get_lan_ip()
    return DeviceInfo(fw=settings.fw_version, ip=ip, port=http_port, name=settings.device_name)
