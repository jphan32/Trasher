"""실기기 하드웨어 구현 (gpiozero). Raspberry Pi(Linux)에서만 import 가능.

macOS/CI에서는 import하지 않는다(factory가 플랫폼 분기). gpiozero가 없으면 명확한 에러.
"""

from __future__ import annotations

from ..config import Settings
from .base import HardwareController, Route
from .belt import build_belt_driver


class GpiozeroHardware(HardwareController):
    def __init__(self, settings: Settings) -> None:
        try:
            from gpiozero import AngularServo  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover - Pi 전용
            raise RuntimeError(
                "gpiozero를 불러올 수 없습니다. "
                "Raspberry Pi에서 `pip install '.[pi]'` 후 실행하세요."
            ) from e

        s = settings.servo
        self._s = settings
        self._gate = AngularServo(s.gate_pin, min_angle=0, max_angle=180)
        self._left = AngularServo(s.left_pin, min_angle=0, max_angle=180)
        self._right = AngularServo(s.right_pin, min_angle=0, max_angle=180)
        # 벨트는 드라이버로 분리(gpiozero GPIO | Hiwonder I2C). config.belt.driver로 선택.
        self._belt = build_belt_driver(settings)
        self.set_gate(open=False)
        self.set_route("center")

    def set_gate(self, *, open: bool) -> None:
        s = self._s.servo
        self._gate.angle = s.gate_open_deg if open else s.gate_closed_deg

    def set_route(self, route: Route) -> None:
        s = self._s.servo
        left_open = route == "left"
        right_open = route == "right"
        self._left.angle = s.diverter_open_deg if left_open else s.diverter_closed_deg
        self._right.angle = s.diverter_open_deg if right_open else s.diverter_closed_deg

    def belt(self, *, on: bool) -> None:
        if on:
            self._belt.run()
        else:
            self._belt.stop()

    def stop_all(self) -> None:
        self._belt.stop()
        self.set_gate(open=False)

    def close(self) -> None:  # pragma: no cover - Pi 전용
        for dev in (self._gate, self._left, self._right, self._belt):
            dev.close()
