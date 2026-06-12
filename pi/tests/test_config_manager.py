"""런타임 튜닝 설정(ConfigManager) — 스키마·검증·clamp·HOT 적용·영속화(delta overlay).

docs/protocol.md §8. HOT은 실제 소비자(MotionDetector·Sorter)로 end-to-end 확인한다.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from trash_sorter.config import Settings
from trash_sorter.config_manager import TUNABLES, ConfigError, ConfigManager
from trash_sorter.hardware.mock import MockHardware
from trash_sorter.hardware.sorter import Sorter
from trash_sorter.protocol import WasteCategory
from trash_sorter.vision.motion import MotionDetector


# --- 조회(snapshot) -------------------------------------------------------
def test_snapshot_has_all_fields_with_metadata() -> None:
    settings = Settings()
    snap = ConfigManager(settings).snapshot()
    assert snap["fw"] == settings.fw_version
    assert len(snap["fields"]) == len(TUNABLES)
    keys = {f["key"] for f in snap["fields"]}
    assert {"belt_run_seconds", "servo_travel_s", "vision_motion_threshold"} <= keys
    belt = next(f for f in snap["fields"] if f["key"] == "belt_run_seconds")
    assert belt["value"] == 3.0
    assert (belt["min"], belt["max"], belt["step"]) == (0.5, 15.0, 0.1)
    assert belt["section"] == "belt" and belt["unit"] == "s" and belt["type"] == "float"


# --- 적용/검증/clamp ------------------------------------------------------
def test_apply_mutates_shared_settings_in_place() -> None:
    settings = Settings()
    result = ConfigManager(settings).apply({"belt_run_seconds": 2.5, "servo_travel_s": 0.9})
    assert result["ok"] is True
    assert result["applied"] == {"belt_run_seconds": 2.5, "servo_travel_s": 0.9}
    assert result["persisted"] is True  # 영속 경로 미설정 → 실패 아님
    assert settings.belt.run_seconds == 2.5
    assert settings.servo.travel_s == 0.9


def test_apply_clamps_to_range() -> None:
    settings = Settings()
    cm = ConfigManager(settings)
    assert cm.apply({"belt_run_seconds": 999})["applied"]["belt_run_seconds"] == 15.0  # max
    assert cm.apply({"belt_run_seconds": 0.0})["applied"]["belt_run_seconds"] == 0.5  # min
    assert settings.belt.run_seconds == 0.5


def test_apply_unknown_field_rejects_all() -> None:
    settings = Settings()
    cm = ConfigManager(settings)
    with pytest.raises(ConfigError):
        cm.apply({"belt_run_seconds": 2.0, "bogus": 1})
    assert settings.belt.run_seconds == 3.0  # 부분 적용 없음(원자성)


def test_apply_rejects_non_number_and_bool() -> None:
    cm = ConfigManager(Settings())
    with pytest.raises(ConfigError):
        cm.apply({"belt_run_seconds": "fast"})
    with pytest.raises(ConfigError):
        cm.apply({"belt_run_seconds": True})  # bool은 숫자로 받지 않는다


def test_apply_empty_is_noop() -> None:
    assert ConfigManager(Settings()).apply({}) == {"ok": True, "applied": {}, "persisted": True}


def test_apply_reports_persist_failure(tmp_path) -> None:
    # 부모가 파일 → mkdir/write 실패(OSError) → persisted False(메모리엔 적용, 비치명).
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    settings = Settings()
    result = ConfigManager(settings, persist_path=blocker / "runtime.json").apply(
        {"belt_run_seconds": 2.0}
    )
    assert result["ok"] is True
    assert result["persisted"] is False  # 디스크 저장 실패를 응답에 노출(iPad 경고용)
    assert settings.belt.run_seconds == 2.0  # 메모리엔 적용됨


# --- HOT: 실제 소비자로 end-to-end 확인 -----------------------------------
def test_belt_seconds_hot_applies_to_sorter() -> None:
    """Sorter가 belt.run_seconds를 매 sort마다 live로 읽는다(in-place 변경 즉시 반영)."""
    settings = Settings()
    cm = ConfigManager(settings)
    slept: list[float] = []
    sorter = Sorter(MockHardware(), settings, sleep=slept.append)

    cm.apply({"belt_run_seconds": 1.0})
    sorter.sort(WasteCategory.PET)
    assert slept[-1] == 1.0

    cm.apply({"belt_run_seconds": 2.5})
    sorter.sort(WasteCategory.CAN)
    assert slept[-1] == 2.5  # 재시작 없이 새 값 반영


def test_motion_threshold_hot_via_provider() -> None:
    """MotionDetector(threshold_provider)가 vision.motion_threshold를 live로 읽는다."""
    settings = Settings()
    cm = ConfigManager(settings)
    det = MotionDetector(threshold_provider=lambda: settings.vision.motion_threshold)
    base = np.zeros((10, 10), dtype=np.uint8)
    changed = base.copy()
    changed[0, :] = 255  # 10/100 = 0.1 변화 비율

    det.is_motion(base)  # prev 프라임(첫 프레임 0.0)
    assert det.is_motion(changed) is True  # 0.1 > 0.02(기본) → 모션

    cm.apply({"vision_motion_threshold": 0.2})
    assert det.is_motion(base) is False  # base↔changed 0.1, 0.1 > 0.2 → 모션 아님(새 임계값)


# --- 영속화(delta overlay) ------------------------------------------------
def test_persist_writes_only_overrides_and_reloads(tmp_path) -> None:
    path = tmp_path / "runtime.json"
    cm1 = ConfigManager(Settings(), persist_path=path)
    cm1.apply({"belt_run_seconds": 2.0, "servo_speed": 0.5})
    # 파일에는 바꾼 키만(delta) 저장
    assert json.loads(path.read_text()) == {"belt_run_seconds": 2.0, "servo_speed": 0.5}

    # 새 프로세스 모사: 깨끗한 Settings에 overlay → 저장값 우선
    settings2 = Settings()
    applied = ConfigManager(settings2, persist_path=path).load_persisted()
    assert applied == {"belt_run_seconds": 2.0, "servo_speed": 0.5}
    assert settings2.belt.run_seconds == 2.0 and settings2.servo.speed == 0.5
    assert settings2.timing.result_timeout_s == 15.0  # 손대지 않은 필드는 env 기본 유지


def test_persist_accumulates_across_puts(tmp_path) -> None:
    path = tmp_path / "runtime.json"
    cm = ConfigManager(Settings(), persist_path=path)
    cm.apply({"belt_run_seconds": 2.0})
    cm.apply({"servo_speed": 0.5})  # 누적되어야 함(이전 키 보존)
    assert json.loads(path.read_text()) == {"belt_run_seconds": 2.0, "servo_speed": 0.5}


def test_load_persisted_clamps_out_of_range(tmp_path) -> None:
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps({"belt_run_seconds": 999}))
    settings = Settings()
    ConfigManager(settings, persist_path=path).load_persisted()
    assert settings.belt.run_seconds == 15.0  # 저장값도 clamp


def test_load_persisted_skips_unknown_and_nonnumber(tmp_path) -> None:
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps({"nope": 1, "belt_run_seconds": "x", "servo_speed": 0.4}))
    settings = Settings()
    applied = ConfigManager(settings, persist_path=path).load_persisted()
    assert applied == {"servo_speed": 0.4}  # 모르는 키·비수치는 건너뜀(전방호환)
    assert settings.servo.speed == 0.4


def test_load_persisted_tolerates_missing_and_corrupt(tmp_path) -> None:
    missing = tmp_path / "absent.json"
    assert ConfigManager(Settings(), persist_path=missing).load_persisted() == {}
    corrupt = tmp_path / "bad.json"
    corrupt.write_text("{not valid json")
    assert ConfigManager(Settings(), persist_path=corrupt).load_persisted() == {}


def test_no_persist_path_is_in_memory(tmp_path) -> None:
    settings = Settings()
    cm = ConfigManager(settings)  # persist_path 없음
    cm.apply({"belt_run_seconds": 4.0})
    assert settings.belt.run_seconds == 4.0
    assert not list(tmp_path.iterdir())  # 어떤 파일도 만들지 않음
