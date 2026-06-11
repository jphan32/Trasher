"""실기기 하드웨어 구현 (gpiozero). Raspberry Pi(Linux)에서만 import 가능.

macOS/CI에서는 import하지 않는다(factory가 플랫폼 분기). gpiozero가 없으면 명확한 에러.

서보는 **SER0043(DF9GMS) 360° 연속회전** — 위치제어가 안 되므로 각도를 쓰지 않는다.
대신 저속(value=±speed)으로 목표 방향으로 ``travel_s`` 동안 구동해 **기구 하드스톱**까지 보낸 뒤
신호를 끊어(detach) 정지한다. 위치는 하드스톱이 물리적으로 유지(연속 스톨/홀딩 전류 없음).
벨트는 별도 드라이버(gpiozero GPIO | Hiwonder I2C, config.belt.driver).
"""

from __future__ import annotations

import time
from collections.abc import Callable

from ..config import Settings
from .base import HardwareController, Route
from .belt import build_belt_driver


def _sign(x: float) -> int:
    return 1 if x >= 0 else -1


def _clamp(v: float) -> float:
    return max(-1.0, min(1.0, v))


class GpiozeroHardware(HardwareController):
    def __init__(
        self, settings: Settings, *, sleep: Callable[[float], None] = time.sleep
    ) -> None:
        try:
            from gpiozero import Servo  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover - Pi 전용
            raise RuntimeError(
                "gpiozero를 불러올 수 없습니다. "
                "Raspberry Pi에서 requirements-pi.txt 설치 후 실행하세요."
            ) from e

        self._s = settings
        self._sleep = sleep
        s = settings.servo
        # initial_value=None → 무신호로 시작(중립 creep 방지). set_* 호출로 위치 확립.
        self._gate = Servo(s.gate_pin, initial_value=None)
        self._left = Servo(s.left_pin, initial_value=None)
        self._right = Servo(s.right_pin, initial_value=None)
        # 벨트는 드라이버로 분리(gpiozero GPIO | Hiwonder I2C). config.belt.driver로 선택.
        self._belt = build_belt_driver(settings)
        # 초기 위치: 게이트 닫힘 + 분기 중앙(좌·우 모두 닫힘)
        self.set_gate(open=False)
        self.set_route("center")

    def _move(self, moves: list[tuple[object, float]]) -> None:
        """(servo, signed_speed) 쌍들을 동시에 저속 구동 → travel_s 후 함께 정지(detach).

        하드스톱이 최대 이동 위치를 제한하므로 시간이 다소 길어도 안전(스톱에 닿아 멈춤).
        정지는 value=None(무신호) — 연속서보 중립 creep과 홀딩 전류를 피한다.
        """
        for servo, val in moves:
            servo.value = _clamp(val)  # type: ignore[attr-defined]
        self._sleep(self._s.servo.travel_s)
        for servo, _ in moves:
            servo.value = None  # type: ignore[attr-defined]

    def set_gate(self, *, open: bool) -> None:
        s = self._s.servo
        direction = _sign(s.gate_dir) * (1 if open else -1)
        self._move([(self._gate, direction * s.speed)])

    def set_route(self, route: Route) -> None:
        s = self._s.servo
        left_dir = _sign(s.left_dir) * (1 if route == "left" else -1)
        right_dir = _sign(s.right_dir) * (1 if route == "right" else -1)
        self._move([(self._left, left_dir * s.speed), (self._right, right_dir * s.speed)])

    def belt(self, *, on: bool) -> None:
        if on:
            self._belt.run()
        else:
            self._belt.stop()

    def stop_all(self) -> None:
        # 비상 정지: 즉시 모든 모션 정지(타임드 이동 없이). 연속서보는 detach=정지.
        self._belt.stop()
        for servo in (self._gate, self._left, self._right):
            servo.value = None

    def close(self) -> None:  # pragma: no cover - Pi 전용
        for dev in (self._gate, self._left, self._right):
            dev.close()
        self._belt.close()
