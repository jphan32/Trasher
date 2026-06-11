"""벨트 모터 드라이버 — 시간 기반 정방향 on/off. 인터페이스 + gpiozero/Hiwonder(I2C) 구현.

벨트는 T_belt초 구동 후 정지뿐이라(docs/protocol.md §2.5) **개루프 PWM으로 충분**하다 —
폐루프(register 0x33)·엔코더 PPR(Hall vs GMR)은 belt 구동에 필요 없다.

- ``GpiozeroBeltDriver``: 현행 GPIO + 모터드라이버(L298N/DRV8871류), gpiozero ``Motor``.
- ``HiwonderBeltDriver``: Hiwonder 4채널 엔코더 모터 드라이버(SA8339/SA8870C)를 I2C로 제어.
  개루프 고정 PWM(register ``0x1f``, 채널별 -100..100)을 쓴다. 전력 한계로 2채널만 사용하며,
  두 모터가 서로 반대 방향을 보고 장착되므로 한 채널의 부호를 뒤집어 같은 선속도 방향을 만든다
  (``invert_a``/``invert_b``, config). 채널·주소·세기는 모두 ``BeltConfig``에서 조정.

실기기 의존(gpiozero/smbus2)은 **생성·버스개방 시점에 지연 import**한다 — 그래서 이 모듈은
macOS에서도 import 가능하고, ``HiwonderBeltDriver``는 fake bus 주입으로 단위테스트된다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..config import Settings

# Hiwonder 4ch 보드(SA8339/SA8870C) I2C 레지스터. 사용자 제공 + 공식 튜토리얼 기준:
#   0x1f = 고정 PWM(개루프, 채널별 signed -100..100)  /  0x33 = 고정 속도(폐루프, 미사용)
# ⚠️ 4채널 블록 레이아웃(0x1f에서 4 signed byte)은 표준 관례 — 실보드/공식 lib로 확정할 것:
#   https://www.hiwonder.com/products/4-channel-encoder-motor-driver
_REG_FIXED_PWM = 0x1F
_NUM_CHANNELS = 4


class BeltDriver(ABC):
    @abstractmethod
    def run(self) -> None:
        """벨트 정방향 구동(시간 기반 — 정지는 호출자가 T_belt 후 stop)."""

    @abstractmethod
    def stop(self) -> None:
        """벨트 정지."""

    def close(self) -> None:  # noqa: B027 - 선택적 override(기본 no-op)
        """리소스 정리."""


class GpiozeroBeltDriver(BeltDriver):
    """GPIO + 모터드라이버. 정방향만 사용(시간 기반 완료)."""

    def __init__(self, settings: Settings) -> None:
        try:
            from gpiozero import Motor  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover - Pi 전용
            raise RuntimeError(
                "gpiozero 없음(벨트). Raspberry Pi에서 requirements-pi.txt 설치 후 실행."
            ) from e
        b = settings.belt
        self._motor = Motor(forward=b.forward_pin, backward=b.backward_pin)

    def run(self) -> None:
        self._motor.forward()

    def stop(self) -> None:
        self._motor.stop()

    def close(self) -> None:  # pragma: no cover - Pi 전용
        self._motor.close()


class HiwonderBeltDriver(BeltDriver):
    """Hiwonder 4ch 엔코더 모터 드라이버(SA8339/SA8870C)를 I2C 개루프 PWM으로 제어.

    ``bus``를 주입하면(테스트) smbus2를 import하지 않는다. None이면 첫 사용 시 지연 open.
    """

    def __init__(self, settings: Settings, *, bus: Any | None = None) -> None:
        b = settings.belt
        self._bus_num = b.i2c_bus
        self._addr = b.i2c_addr
        self._pwm = max(0, min(100, b.pwm))
        self._ch_a = b.ch_a
        self._ch_b = b.ch_b
        self._sign_a = -1 if b.invert_a else 1
        self._sign_b = -1 if b.invert_b else 1
        for ch in (self._ch_a, self._ch_b):
            if not 0 <= ch < _NUM_CHANNELS:
                raise ValueError(f"belt 채널 인덱스 범위 밖(0..{_NUM_CHANNELS - 1}): {ch}")
        self._bus = bus

    def _get_bus(self) -> Any:
        if self._bus is None:
            import smbus2  # 지연 import — Pi 런타임 전용(테스트는 bus 주입)

            self._bus = smbus2.SMBus(self._bus_num)
        return self._bus

    def _write_pwm(self, pwm_a: int, pwm_b: int) -> None:
        # 미사용 채널은 0. signed(-100..100) → uint8 2의 보수 바이트.
        values = [0] * _NUM_CHANNELS
        values[self._ch_a] = pwm_a
        values[self._ch_b] = pwm_b
        data = [v & 0xFF for v in values]
        self._get_bus().write_i2c_block_data(self._addr, _REG_FIXED_PWM, data)

    def run(self) -> None:
        self._write_pwm(self._sign_a * self._pwm, self._sign_b * self._pwm)

    def stop(self) -> None:
        self._write_pwm(0, 0)

    def close(self) -> None:
        # 정지 시도 후 버스 닫기. 정리 단계라 I2C 오류는 무시(베스트-에포트).
        try:
            self.stop()
        except OSError:
            pass
        if self._bus is not None:
            try:
                self._bus.close()
            except OSError:
                pass


def build_belt_driver(settings: Settings, *, bus: Any | None = None) -> BeltDriver:
    """config의 ``belt.driver``로 드라이버 선택. ``bus``는 Hiwonder 테스트 주입용."""
    name = settings.belt.driver.strip().lower()
    if name == "hiwonder":
        return HiwonderBeltDriver(settings, bus=bus)
    if name == "gpiozero":
        return GpiozeroBeltDriver(settings)
    raise ValueError(f"알 수 없는 벨트 드라이버: {settings.belt.driver!r} (gpiozero|hiwonder)")
