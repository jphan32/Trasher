"""상태 표시 OLED — Pi 동작 상태를 현장 운영자가 즉시 확인.

구성(벨트·버튼과 같은 분리 패턴):
- ``StatusDisplay``(ABC) + ``DisplaySnapshot``(표시 데이터) + ``MockDisplay``(호스트, 프레임 기록)
  + ``LumaOledDisplay``(실기기, luma.oled 지연 import).
- 오케스트레이터가 매 tick ``DisplaySnapshot``을 구성해 레이트리밋으로 ``render``한다(app.py).

대상: **YWROBOT 12864 I2C OLED = 128×64**. 제어칩은 보통 **SSD1306**(0x3C); 변종이 **SH1106**이면
``DisplayConfig.controller='sh1106'``. luma.oled는 둘 다 지원. docs/hardware.md "상태 OLED".

표시는 **ASCII/영문**으로 한다 — luma 기본 폰트는 한글 글리프가 없고, 이 화면은 **참여자가 아닌
운영자용 진단 표시**라 영문 약어로 충분하다(참여자 대면 UI는 iPad). 큰 상태 글자는 시스템 TTF가
있으면 사용하고 없으면 기본 폰트로 폴백한다.

luma/Pillow는 Pi 전용이라 **지연 import**한다 — macOS에서도 import되고 Mock으로 테스트된다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..config import Settings
from ..protocol import ErrorCode, PiState, WasteCategory


@dataclass(frozen=True)
class DisplaySnapshot:
    """OLED에 그릴 한 프레임의 상태. 동등성(==)으로 '변경됨'을 판정해 불필요한 재렌더를 막는다."""

    state: PiState
    cycle: int
    started: bool                       # §2.1 게이팅: 감지 켜짐 여부(idle=READY/PAUSED 구분)
    err: ErrorCode | None
    last_sort: WasteCategory | None
    ble_connected: bool                 # Central(iPad) 연결 추정(best-effort)
    ip: str
    name: str


# 상태 → 화면 라벨(영문 약어, 운영자용). idle은 started 여부로 READY/PAUSED 구분(아래 _state_label).
_STATE_LABEL: dict[PiState, str] = {
    PiState.DETECTING: "DETECT",
    PiState.CAPTURING: "CAPTURE",
    PiState.AWAITING_RESULT: "WAIT AI",
    PiState.SORTING: "SORTING",
    PiState.ERROR: "ERROR",
    PiState.MAINTENANCE: "MAINT",
}
_SPINNER = "|/-\\"


def _state_label(snap: DisplaySnapshot) -> str:
    if snap.state is PiState.IDLE:
        return "READY" if snap.started else "PAUSED"
    return _STATE_LABEL.get(snap.state, snap.state.value.upper()[:7])


class StatusDisplay(ABC):
    @abstractmethod
    def render(self, snapshot: DisplaySnapshot, *, spinner: int = 0) -> None:
        """상태를 화면에 출력. ``spinner``는 살아있음 표시용 회전 인덱스(0..)."""

    def close(self) -> None:  # noqa: B027 - 선택적 override(기본 no-op)
        """리소스 정리(화면 클리어/버스 닫기)."""


@dataclass
class MockDisplay(StatusDisplay):
    """호스트(macOS/CI) 테스트용. 렌더된 스냅샷·스피너를 이력에 기록한다."""

    frames: list[DisplaySnapshot] = field(default_factory=list)
    spinners: list[int] = field(default_factory=list)
    closed: bool = False

    def render(self, snapshot: DisplaySnapshot, *, spinner: int = 0) -> None:
        self.frames.append(snapshot)
        self.spinners.append(spinner)

    def close(self) -> None:
        self.closed = True


# 큰 상태 글자에 쓸 시스템 TTF 후보(Debian 기본 위치). 없으면 PIL 기본 비트맵 폰트로 폴백.
_TTF_BOLD = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)
_TTF_REG = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)


class LumaOledDisplay(StatusDisplay):
    """실기기 I2C OLED(luma.oled). SSD1306/SH1106 선택, 128×64 레이아웃."""

    def __init__(self, settings: Settings) -> None:
        d = settings.display
        try:
            from luma.core.interface.serial import i2c  # type: ignore[import-not-found]

            if d.controller.strip().lower() == "sh1106":
                from luma.oled.device import sh1106 as device_ctor  # type: ignore[import-not-found]
            else:
                from luma.oled.device import (
                    ssd1306 as device_ctor,  # type: ignore[import-not-found]
                )
        except ImportError as e:  # pragma: no cover - Pi 전용
            raise RuntimeError(
                "luma.oled를 불러올 수 없습니다(OLED). "
                "Raspberry Pi에서 requirements-pi.txt 설치 + I2C 활성화 후 실행하세요."
            ) from e
        serial = i2c(port=d.i2c_bus, address=d.i2c_addr)
        self._device = device_ctor(serial, width=d.width, height=d.height, rotate=d.rotate % 4)
        self._w = d.width
        self._h = d.height
        self._big, self._small = self._load_fonts()

    @staticmethod
    def _load_fonts() -> tuple[Any, Any]:
        from PIL import ImageFont  # type: ignore[import-not-found]

        small = ImageFont.load_default()
        big = small
        for bold in _TTF_BOLD:
            try:
                big = ImageFont.truetype(bold, 22)
                break
            except OSError:
                continue
        for reg in _TTF_REG:
            try:
                small = ImageFont.truetype(reg, 11)
                break
            except OSError:
                continue
        return big, small

    def _textw(self, draw: Any, text: str, font: Any) -> int:
        try:
            return int(draw.textlength(text, font=font))
        except (AttributeError, TypeError):  # 구형 Pillow 폴백
            return len(text) * 6

    def render(self, snapshot: DisplaySnapshot, *, spinner: int = 0) -> None:
        from luma.core.render import canvas  # type: ignore[import-not-found]

        spin = _SPINNER[spinner % len(_SPINNER)]
        last = snapshot.last_sort.value.upper() if snapshot.last_sort else "-"
        ble = "ok" if snapshot.ble_connected else "--"
        with canvas(self._device) as draw:
            # 헤더: 장치명(좌) + IP(우) — 운영자가 Pi를 식별/찾기 위함.
            draw.text((0, 0), snapshot.name[:14], font=self._small, fill=255)
            if snapshot.ip:
                ipw = self._textw(draw, snapshot.ip, self._small)
                draw.text((self._w - ipw, 0), snapshot.ip, font=self._small, fill=255)
            # 큰 상태 글자(중앙 세로). + 우측에 회전 스피너(살아있음 표시).
            label = _state_label(snapshot)
            draw.text((0, 15), label, font=self._big, fill=255)
            draw.text((self._w - 7, 14), spin, font=self._small, fill=255)
            # 하단 1행: cycle + 이번 결과
            draw.text((0, 44), f"C{snapshot.cycle}  {last}", font=self._small, fill=255)
            # 하단 2행: 오류가 있으면 오류코드(우선), 없으면 BLE 연결 상태
            bottom = snapshot.err.value if snapshot.err else f"BLE {ble}"
            draw.text((0, 53), bottom[:21], font=self._small, fill=255)

    def close(self) -> None:  # pragma: no cover - Pi 전용
        try:
            self._device.cleanup()  # 화면 클리어 + 직렬 닫기
        except Exception:  # noqa: BLE001 - 정리 단계, 베스트에포트
            pass
