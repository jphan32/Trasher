"""벨트 모터 드라이버 — 시간 기반 정방향 on/off. 인터페이스 + gpiozero/Hiwonder(I2C) 구현.

벨트는 T_belt초 구동 후 정지뿐이라(docs/protocol.md §2.5) **개루프 PWM으로 충분**하다 —
폐루프(register 0x33)·엔코더 PPR(Hall vs GMR)은 belt 구동에 필요 없다.

- ``GpiozeroBeltDriver``: 현행 GPIO + 모터드라이버(L298N/DRV8871류), gpiozero ``Motor``.
- ``HiwonderBeltDriver``: Hiwonder 4채널 엔코더 모터 드라이버(SA8870C)를 I2C로 제어.
  개루프 고정 PWM(register ``0x1f``, 채널별 -100..100)을 쓴다. 전력 한계로 2채널만 사용하며,
  두 모터가 서로 반대 방향을 보고 장착되므로 한 채널의 부호를 뒤집어 같은 선속도 방향을 만든다
  (``invert_a``/``invert_b``, config). 채널·주소·세기는 모두 ``BeltConfig``에서 조정.

실기기 의존(gpiozero/smbus2)은 **생성·버스개방 시점에 지연 import**한다 — 그래서 이 모듈은
macOS에서도 import 가능하고, ``HiwonderBeltDriver``는 fake bus 주입으로 단위테스트된다.
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from typing import Any

from ..config import Settings

# Hiwonder 4ch 보드(SA8870C) I2C 레지스터(공식 SDK 검증, decimal 20/21/51/60 = 아래 hex):
#   0x14=MOTOR_TYPE(3=JGB37-520) · 0x15=ENCODER_POLARITY · 0x33=고정속도(폐루프, 4×signed)
#   0x3C=엔코더. 개루프(0x1f)는 이 모터를 못 돌려 미사용 — 폐루프(0x33)만 구동(trash-bjl).
_REG_MOTOR_TYPE = 0x14
_REG_ENCODER_POLARITY = 0x15
_REG_FIXED_SPEED = 0x33
_NUM_CHANNELS = 4
# MOTOR_TYPE 적용 대기(공식 SDK 타이밍). 모듈 상수라 테스트에서 0으로 monkeypatch 가능.
_INIT_TYPE_DELAY_S = 0.5
_INIT_POLARITY_DELAY_S = 0.05


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
    """Hiwonder 4ch 엔코더 모터 드라이버(SA8870C)를 I2C **폐루프 고정속도(0x33)** 로 제어.

    실기기 확정(trash-bjl): 개루프(0x1f)는 이 모터를 못 돌리고, 보드 MCU가 엔코더로 속도를
    제어하는 폐루프(0x33)만 강하게·안정적으로 구동된다. ⚠️ **보드 I2C VCC=5V 필수**(3.3V는 MCU
    언더파워 → 구동 중 I2C 행). 속도 명령은 보드 watchdog로 ~0.3s 후 감쇠하므로 ``run`` 은
    백그라운드 스레드로 ``refresh_s`` 마다 재전송해 연속 회전, ``stop`` 이 스레드 정지+속도0.
    단일 모터(``channel``). ``bus`` 주입 시 smbus2 import 생략(테스트).
    """

    def __init__(self, settings: Settings, *, bus: Any | None = None) -> None:
        b = settings.belt
        self._bus_num = b.i2c_bus
        self._addr = b.i2c_addr
        self._channel = b.channel
        self._speed = max(-100, min(100, b.speed))  # 폐루프 고정속도(부호=방향)
        self._motor_type = b.motor_type
        self._polarity = b.encoder_polarity
        self._refresh_s = max(0.0, b.refresh_s)
        if not 0 <= self._channel < _NUM_CHANNELS:
            raise ValueError(f"belt 채널 인덱스 범위 밖(0..{_NUM_CHANNELS - 1}): {self._channel}")
        self._bus = bus
        self._inited = False
        self._lock = threading.Lock()  # 메인루프(run/stop)와 재전송 스레드의 버스 접근 직렬화
        self._refresh: threading.Thread | None = None
        self._running = False

    def _get_bus(self) -> Any:
        if self._bus is None:
            import smbus2  # 지연 import — Pi 런타임 전용(테스트는 bus 주입)

            self._bus = smbus2.SMBus(self._bus_num)
        return self._bus

    def _ensure_init(self) -> None:
        # MOTOR_TYPE·극성 설정(공식 SDK 타이밍: 타입 후 0.5s). 출력 enable의 전제조건.
        if self._inited:
            return
        bus = self._get_bus()
        bus.write_byte_data(self._addr, _REG_MOTOR_TYPE, self._motor_type)
        time.sleep(_INIT_TYPE_DELAY_S)
        bus.write_byte_data(self._addr, _REG_ENCODER_POLARITY, self._polarity)
        time.sleep(_INIT_POLARITY_DELAY_S)
        self._inited = True

    def _write_speed(self, speed: int) -> None:
        values = [0] * _NUM_CHANNELS
        values[self._channel] = speed & 0xFF  # signed int8 2의 보수
        self._get_bus().write_i2c_block_data(self._addr, _REG_FIXED_SPEED, values)

    def run(self) -> None:
        """폐루프 정속 구동 시작(논블로킹). 재전송 스레드로 watchdog 감쇠를 막아 연속 회전."""
        self._ensure_init()
        self._running = True
        with self._lock:
            self._write_speed(self._speed)
        if self._refresh_s > 0 and (self._refresh is None or not self._refresh.is_alive()):
            self._refresh = threading.Thread(target=self._refresh_loop, daemon=True)
            self._refresh.start()

    def _refresh_loop(self) -> None:
        while self._running:
            with self._lock:
                try:
                    self._write_speed(self._speed)
                except OSError:
                    pass  # 일시적 I2C 오류는 다음 주기에 재시도(루프·모터 보호)
            time.sleep(self._refresh_s)

    def stop(self) -> None:
        """재전송 중지 + 속도 0(보드가 폐루프로 정지·홀드)."""
        self._running = False
        thread = self._refresh
        if thread is not None:
            thread.join(timeout=max(0.2, self._refresh_s * 4))
            self._refresh = None
        with self._lock:
            try:
                self._write_speed(0)
                self._write_speed(0)  # 한 번 더(확실 정지)
            except OSError:
                pass

    def close(self) -> None:
        # 정지 시도 후 버스 닫기. 정리 단계라 I2C 오류는 무시(베스트-에포트).
        self.stop()
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
