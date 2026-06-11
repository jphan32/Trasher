"""벨트 드라이버 단위테스트 — Hiwonder I2C 로직을 fake bus로 검증(하드웨어 불필요).

라이브 I2C는 Pi의 i2c_arm 활성화 + 보드 배선 후에야 가능(trash-bjl). 그 전까지 '현재 가능한
수준'은 이 fake-bus 테스트 — 채널/부호/클램프/정지/주소·블록 형식을 결정적으로 검증한다.
"""

from __future__ import annotations

import pytest

from trash_sorter.config import load_settings
from trash_sorter.hardware.belt import (
    HiwonderBeltDriver,
    build_belt_driver,
)

REG_FIXED_PWM = 0x1F


class FakeBus:
    """smbus2.SMBus 대역 — write_i2c_block_data/close 호출을 기록."""

    def __init__(self) -> None:
        self.writes: list[tuple[int, int, list[int]]] = []
        self.closed = False

    def write_i2c_block_data(self, addr: int, reg: int, data: list[int]) -> None:
        self.writes.append((addr, reg, list(data)))

    def close(self) -> None:
        self.closed = True


def _settings(monkeypatch: pytest.MonkeyPatch, **env: object):
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


# --- Hiwonder 개루프 PWM 로직 ------------------------------------------------


def test_run_writes_signed_pwm_to_configured_channels(monkeypatch: pytest.MonkeyPatch) -> None:
    # 기본: ch_a=0(+), ch_b=1(invert_b=True → -), pwm=60, addr=0x34.
    bus = FakeBus()
    HiwonderBeltDriver(_settings(monkeypatch), bus=bus).run()
    addr, reg, data = bus.writes[-1]
    assert addr == 0x34
    assert reg == REG_FIXED_PWM
    # ch0=+60, ch1=-60(=0xC4), ch2·3=0. 미러 2모터가 같은 선속도 방향을 내도록 부호 반전.
    assert data == [60, (-60) & 0xFF, 0, 0]
    assert data[1] == 0xC4


def test_stop_writes_zeros(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = FakeBus()
    HiwonderBeltDriver(_settings(monkeypatch), bus=bus).stop()
    assert bus.writes[-1] == (0x34, REG_FIXED_PWM, [0, 0, 0, 0])


def test_pwm_is_clamped_to_100(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = FakeBus()
    s = _settings(monkeypatch, TRASH_BELT_PWM=150)
    HiwonderBeltDriver(s, bus=bus).run()
    _, _, data = bus.writes[-1]
    assert data == [100, (-100) & 0xFF, 0, 0]


def test_invert_flags_control_signs(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = FakeBus()
    s = _settings(monkeypatch, TRASH_BELT_INVERT_A="true", TRASH_BELT_INVERT_B="false")
    HiwonderBeltDriver(s, bus=bus).run()
    _, _, data = bus.writes[-1]
    assert data == [(-60) & 0xFF, 60, 0, 0]  # a 반전, b 정


def test_custom_channels_place_values(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = FakeBus()
    s = _settings(monkeypatch, TRASH_BELT_CH_A=2, TRASH_BELT_CH_B=3)
    HiwonderBeltDriver(s, bus=bus).run()
    _, _, data = bus.writes[-1]
    assert data == [0, 0, 60, (-60) & 0xFF]


def test_channel_out_of_range_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _settings(monkeypatch, TRASH_BELT_CH_B=4)  # 0..3만 유효
    with pytest.raises(ValueError, match="채널 인덱스"):
        HiwonderBeltDriver(s, bus=FakeBus())


def test_i2c_addr_accepts_hex_env(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = FakeBus()
    s = _settings(monkeypatch, TRASH_BELT_I2C_ADDR="0x40")
    HiwonderBeltDriver(s, bus=bus).run()
    assert bus.writes[-1][0] == 0x40


def test_close_stops_then_closes_bus(monkeypatch: pytest.MonkeyPatch) -> None:
    bus = FakeBus()
    HiwonderBeltDriver(_settings(monkeypatch), bus=bus).close()
    assert bus.writes[-1] == (0x34, REG_FIXED_PWM, [0, 0, 0, 0])  # 정지 먼저
    assert bus.closed is True
