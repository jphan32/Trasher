"""벨트 드라이버 단위테스트 — Hiwonder **폐루프 고정속도(0x33)** 로직을 fake bus로 검증.

실기기 확정(trash-bjl): 개루프(0x1f)는 이 모터를 못 돌리고 폐루프(0x33)+MOTOR_TYPE 초기화로
구동된다. ⚠️ 보드 I2C VCC=5V 필수(3.3V는 구동 중 I2C 행). 라이브 검증은 보드+5V에서.
"""

from __future__ import annotations

import time

import pytest

from trash_sorter.config import load_settings
from trash_sorter.hardware import belt as belt_mod
from trash_sorter.hardware.belt import HiwonderBeltDriver, build_belt_driver

REG_MOTOR_TYPE = 0x14
REG_POLARITY = 0x15
REG_FIXED_SPEED = 0x33


class FakeBus:
    """smbus2.SMBus 대역 — 블록/바이트 write·close 호출을 기록."""

    def __init__(self) -> None:
        self.block_writes: list[tuple[int, int, list[int]]] = []  # (addr, reg, data)
        self.byte_writes: list[tuple[int, int, int]] = []  # (addr, reg, value)
        self.closed = False

    def write_i2c_block_data(self, addr: int, reg: int, data: list[int]) -> None:
        self.block_writes.append((addr, reg, list(data)))

    def write_byte_data(self, addr: int, reg: int, value: int) -> None:
        self.byte_writes.append((addr, reg, value))

    def close(self) -> None:
        self.closed = True


@pytest.fixture(autouse=True)
def _no_init_delay(monkeypatch: pytest.MonkeyPatch):
    # init의 SDK 타이밍 sleep을 0으로(테스트 가속). 재전송 스레드의 time.sleep은 영향 없음.
    monkeypatch.setattr(belt_mod, "_INIT_TYPE_DELAY_S", 0.0)
    monkeypatch.setattr(belt_mod, "_INIT_POLARITY_DELAY_S", 0.0)


def _settings(monkeypatch: pytest.MonkeyPatch, **env: object):
    monkeypatch.setenv("TRASH_BELT_REFRESH", "0")  # 기본: 재전송 스레드 없음(결정적)
    for k, v in env.items():
        monkeypatch.setenv(k, str(v))
    return load_settings()


# --- 드라이버 선택 -----------------------------------------------------------
def test_build_selects_hiwonder(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, TRASH_BELT_DRIVER="hiwonder")
    assert isinstance(build_belt_driver(s, bus=FakeBus()), HiwonderBeltDriver)


def test_build_unknown_driver_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, TRASH_BELT_DRIVER="nope")
    with pytest.raises(ValueError, match="벨트 드라이버"):
        build_belt_driver(s)


def test_build_gpiozero_needs_gpiozero(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("gpiozero")  # macOS 미설치 → skip
    s = _settings(monkeypatch, TRASH_BELT_DRIVER="gpiozero")
    build_belt_driver(s)


# --- Hiwonder 폐루프 로직 ----------------------------------------------------
def test_run_inits_type_polarity_then_writes_speed(monkeypatch: pytest.MonkeyPatch) -> None:
    # run: MOTOR_TYPE(0x14)+극성(0x15) 설정 후 0x33에 채널별 signed speed 기록.
    bus = FakeBus()
    HiwonderBeltDriver(_settings(monkeypatch), bus=bus).run()  # 기본 channel=1, speed=-50, type=3
    assert (0x34, REG_MOTOR_TYPE, 3) in bus.byte_writes
    assert (0x34, REG_POLARITY, 0) in bus.byte_writes
    addr, reg, data = bus.block_writes[-1]
    assert addr == 0x34 and reg == REG_FIXED_SPEED
    assert data == [0, (-50) & 0xFF, 0, 0]  # channel 1 = -50(=0xCE), 나머지 0
    assert data[1] == 0xCE


def test_stop_writes_zero_speed(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = FakeBus()
    d = HiwonderBeltDriver(_settings(monkeypatch), bus=bus)
    d.run()
    d.stop()
    assert bus.block_writes[-1] == (0x34, REG_FIXED_SPEED, [0, 0, 0, 0])


def test_speed_clamped_to_signed_100(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = FakeBus()
    s = _settings(monkeypatch, TRASH_BELT_SPEED=-150)
    HiwonderBeltDriver(s, bus=bus).run()
    _, _, data = bus.block_writes[-1]
    assert data == [0, (-100) & 0xFF, 0, 0]


def test_custom_channel_places_speed(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = FakeBus()
    s = _settings(monkeypatch, TRASH_BELT_CHANNEL=2, TRASH_BELT_SPEED=40)
    HiwonderBeltDriver(s, bus=bus).run()
    _, _, data = bus.block_writes[-1]
    assert data == [0, 0, 40, 0]


def test_polarity_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = FakeBus()
    s = _settings(monkeypatch, TRASH_BELT_POLARITY=1)
    HiwonderBeltDriver(s, bus=bus).run()
    assert (0x34, REG_POLARITY, 1) in bus.byte_writes


def test_channel_out_of_range_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, TRASH_BELT_CHANNEL=4)  # 0..3만 유효
    with pytest.raises(ValueError, match="채널 인덱스"):
        HiwonderBeltDriver(s, bus=FakeBus())


def test_i2c_addr_accepts_hex_env(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = FakeBus()
    s = _settings(monkeypatch, TRASH_BELT_I2C_ADDR="0x40")
    HiwonderBeltDriver(s, bus=bus).run()
    assert bus.block_writes[-1][0] == 0x40


def test_close_stops_then_closes_bus(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = FakeBus()
    d = HiwonderBeltDriver(_settings(monkeypatch), bus=bus)
    d.run()
    d.close()
    assert bus.block_writes[-1] == (0x34, REG_FIXED_SPEED, [0, 0, 0, 0])  # 정지 먼저
    assert bus.closed is True


def test_refresh_thread_resends_then_stop_halts(monkeypatch: pytest.MonkeyPatch) -> None:
    # refresh_s>0: run이 재전송 스레드 시작 → speed를 여러 번 기록, stop이 스레드 종료.
    bus = FakeBus()
    s = _settings(monkeypatch, TRASH_BELT_REFRESH="0.01")
    d = HiwonderBeltDriver(s, bus=bus)
    d.run()
    time.sleep(0.06)
    d.stop()  # 스레드 join → 이후 writes 안정
    drive = (0x34, REG_FIXED_SPEED, [0, (-50) & 0xFF, 0, 0])
    assert bus.block_writes.count(drive) >= 2  # 재전송됨
    assert bus.block_writes[-1] == (0x34, REG_FIXED_SPEED, [0, 0, 0, 0])  # stop=0
    n = len(bus.block_writes)
    time.sleep(0.03)
    assert len(bus.block_writes) == n  # 정지 후 추가 write 없음(스레드 종료 확인)
