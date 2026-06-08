"""플랫폼 감지/조립 테스트. is_raspberry_pi는 실제 Pi만 True여야 한다."""

from __future__ import annotations

from trash_sorter.config import load_settings
from trash_sorter.factory import build_app, device_info, is_raspberry_pi, use_mock_default


def test_is_raspberry_pi_false_on_dev_machine() -> None:
    # macOS/CI(비-Pi)에서는 False → Mock 선택.
    assert is_raspberry_pi() is False


def test_use_mock_default_env_override(monkeypatch) -> None:
    monkeypatch.delenv("TRASH_MOCK", raising=False)
    assert use_mock_default() is True  # 비-Pi → mock

    monkeypatch.setenv("TRASH_MOCK", "0")
    assert use_mock_default() is False  # override: 실기기 강제

    monkeypatch.setenv("TRASH_MOCK", "1")
    assert use_mock_default() is True


def test_build_app_mock_wires_everything() -> None:
    ctx = build_app(load_settings(), mock=True)
    assert ctx.orchestrator is not None
    assert ctx.ble is not None and ctx.photo_server is not None


def test_device_info_uses_advertised_ip(monkeypatch) -> None:
    monkeypatch.setenv("TRASH_ADVERTISED_IP", "10.1.2.3")
    di = device_info(load_settings(), http_port=9000)
    assert di.ip == "10.1.2.3"
    assert di.port == 9000
    assert di.proto == 1
