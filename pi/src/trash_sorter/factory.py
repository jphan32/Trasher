"""플랫폼 분기 조립. Linux(Pi)=실기기 구현, 그 외=Mock. docs/protocol.md 전반.

macOS/CI에서 import해도 안전하도록 실기기 구현은 **함수 내부에서 지연 import**한다.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .app import Orchestrator
from .ble.base import BleServer
from .classify import build_classifier
from .config import Settings, load_settings
from .hardware.base import HardwareController
from .hardware.button import ButtonInput
from .hardware.display import StatusDisplay
from .protocol import DeviceInfo
from .state import StateMachine
from .vision.base import Camera
from .vision.motion import MotionDetector
from .web.photo_server import PhotoServer, PhotoStore, get_lan_ip

log = logging.getLogger(__name__)


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


def _component_mock(name: str, default: bool) -> bool:
    """컴포넌트별 mock override(TRASH_MOCK_HARDWARE/CAMERA/BLE). 미설정이면 전역 ``default``.

    실기기에서 '모터만 제외' 부분 구성을 위해: 예) TRASH_MOCK_HARDWARE=1 → 서보/벨트만 Mock,
    카메라·BLE는 실기기 유지(iPad 연결·사이클은 살리고 모터 구동만 배제).
    """
    override = os.environ.get(name)
    if override is None:
        return default
    return override.strip().lower() in ("1", "true", "on", "yes")


@dataclass
class AppContext:
    orchestrator: Orchestrator
    ble: BleServer
    photo_server: PhotoServer
    hardware: HardwareController
    camera: Camera
    button: ButtonInput | None = None
    display: StatusDisplay | None = None


def _build_hardware(settings: Settings, mock: bool) -> HardwareController:
    if mock:
        from .hardware.mock import MockHardware

        return MockHardware()
    from .hardware.gpiozero_impl import GpiozeroHardware

    return GpiozeroHardware(settings)


def _build_button(settings: Settings, mock: bool) -> ButtonInput | None:
    """리셋 버튼. 비활성(enabled=False)이면 None. 실기기 생성 실패는 비치명(없이 진행)."""
    if not settings.button.enabled:
        return None
    if mock:
        from .hardware.button import MockButton

        return MockButton()
    try:
        from .hardware.button import GpiozeroButton

        return GpiozeroButton(settings)
    except Exception as e:  # noqa: BLE001 - 버튼 미배선/핀 충돌은 비치명 → 버튼 없이 운영
        log.warning("리셋 버튼 초기화 실패 — 버튼 없이 진행: %s", e)
        return None


def _build_display(settings: Settings, mock: bool) -> StatusDisplay | None:
    """상태 OLED. 비활성(enabled=False)이면 None. I2C 미활성/미배선 실패는 비치명(없이 진행)."""
    if not settings.display.enabled:
        return None
    if mock:
        from .hardware.display import MockDisplay

        return MockDisplay()
    try:
        from .hardware.display import LumaOledDisplay

        return LumaOledDisplay(settings)
    except Exception as e:  # noqa: BLE001 - OLED 미배선/I2C 미활성은 비치명 → 표시 없이 운영
        log.warning("상태 OLED 초기화 실패 — 표시 없이 진행: %s", e)
        return None


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
    # 컴포넌트별 override — '모터만 제외'(TRASH_MOCK_HARDWARE=1) 같은 실기기 부분 구성 지원.
    mock_hw = _component_mock("TRASH_MOCK_HARDWARE", use_mock)
    mock_cam = _component_mock("TRASH_MOCK_CAMERA", use_mock)
    mock_ble = _component_mock("TRASH_MOCK_BLE", use_mock)
    log.info("mock 구성: hardware=%s camera=%s ble=%s", mock_hw, mock_cam, mock_ble)

    # 사진 디렉터리: 명시(TRASH_PHOTO_DIR) > mock 임시디렉터리 > 실기기 기본(/var/tmp).
    # 명시 경로는 E2E/운영에서 사진을 고정 위치에 시드·검사할 때 쓴다(config.photo_dir).
    photo_dir = settings.network.photo_dir or (
        tempfile.mkdtemp(prefix="trash-photos-") if use_mock else "/var/tmp/trash-photos"
    )
    store = PhotoStore(photo_dir, retention=settings.network.photo_retention)
    # 분류기: SA 키 있으면 Gemini, 없으면 Mock(dev/sim). 사진서버 /classify에서 사용.
    classifier = build_classifier()
    photo_server = PhotoServer(store, port=settings.network.http_port, classifier=classifier)

    hardware = _build_hardware(settings, mock_hw)
    camera = _build_camera(settings, mock_cam)
    ble = _build_ble(settings, mock_ble)
    # 버튼·OLED는 하드웨어 계층 — 모터와 같은 mock(TRASH_MOCK_HARDWARE) 분기. 각각 enabled 플래그.
    button = _build_button(settings, mock_hw)
    display = _build_display(settings, mock_hw)

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
        button=button,
        display=display,
    )

    # DeviceInfo는 HTTP 포트가 정해진 뒤(서버 시작 후) set_device_info로 갱신.
    return AppContext(
        orchestrator=orchestrator,
        ble=ble,
        photo_server=photo_server,
        hardware=hardware,
        camera=camera,
        button=button,
        display=display,
    )


def device_info(settings: Settings, http_port: int) -> DeviceInfo:
    ip = settings.network.advertised_ip or get_lan_ip()
    return DeviceInfo(fw=settings.fw_version, ip=ip, port=http_port, name=settings.device_name)
