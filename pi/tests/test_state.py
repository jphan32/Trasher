"""상태 머신 전이 규칙 테스트. docs/protocol.md §2."""

from __future__ import annotations

import pytest

from trash_sorter.protocol import ErrorCode, PiState, WasteCategory
from trash_sorter.state import InvalidTransition, StateMachine


def _run_to_awaiting(sm: StateMachine) -> int:
    sm.start()
    assert sm.begin_detection() is True
    sm.begin_capture()
    return sm.photo_captured()


def test_gating_blocks_detection_until_started() -> None:
    sm = StateMachine()
    assert sm.begin_detection() is False  # start 전엔 감지 안 함
    assert sm.state is PiState.IDLE
    sm.start()
    assert sm.begin_detection() is True
    assert sm.state is PiState.DETECTING


def test_happy_path_cycle() -> None:
    sm = StateMachine()
    cycle = _run_to_awaiting(sm)
    assert sm.state is PiState.AWAITING_RESULT
    assert cycle == 1
    assert sm.result(cycle, WasteCategory.PET) is True
    assert sm.state is PiState.SORTING
    assert sm.pending_sort is WasteCategory.PET
    sm.sort_complete()
    assert sm.state is PiState.IDLE
    assert sm.snapshot().last_sort is WasteCategory.PET


def test_stale_result_discarded() -> None:
    sm = StateMachine()
    cycle = _run_to_awaiting(sm)
    assert sm.result(cycle - 1, WasteCategory.CAN) is False  # cycle 불일치
    assert sm.state is PiState.AWAITING_RESULT


def test_result_timeout_falls_back_to_other() -> None:
    sm = StateMachine()
    _run_to_awaiting(sm)
    sm.result_timeout()
    assert sm.state is PiState.SORTING
    assert sm.pending_sort is WasteCategory.OTHER
    assert sm.snapshot().err is ErrorCode.RESULT_TIMEOUT


def test_seq_monotonic() -> None:
    sm = StateMachine()
    a = sm.snapshot().seq
    b = sm.snapshot().seq
    assert b == a + 1


def test_cycle_increments_per_detection() -> None:
    sm = StateMachine()
    sm.start()
    sm.begin_detection()
    sm.begin_capture()
    sm.photo_captured()
    sm.result(1, WasteCategory.OTHER)
    sm.sort_complete()
    assert sm.begin_detection() is True
    assert sm.cycle == 2


def test_estop_and_reset() -> None:
    sm = StateMachine()
    _run_to_awaiting(sm)
    sm.estop()
    assert sm.state is PiState.ERROR
    assert sm.snapshot().err is ErrorCode.ESTOPPED
    sm.reset()
    assert sm.state is PiState.IDLE


def test_maintenance_toggle() -> None:
    sm = StateMachine()
    sm.set_maintenance(True)
    assert sm.state is PiState.MAINTENANCE
    sm.set_maintenance(False)
    assert sm.state is PiState.IDLE


def test_last_sort_is_cycle_scoped() -> None:
    sm = StateMachine()
    sm.start()
    sm.begin_detection()
    sm.begin_capture()
    sm.photo_captured()
    sm.result(1, WasteCategory.CAN)
    sm.sort_complete()
    assert sm.snapshot().last_sort is WasteCategory.CAN  # 완료 후 유지(reward 표시용)
    sm.begin_detection()  # 새 cycle
    assert sm.snapshot().last_sort is None  # 클리어 — 이전 결과로 오인 reward 방지


def test_reset_and_maintenance_clear_last_sort() -> None:
    for abort in ("reset", "maintenance"):
        sm = StateMachine()
        sm.start()
        sm.begin_detection()
        sm.begin_capture()
        sm.photo_captured()
        sm.result(1, WasteCategory.PET)
        sm.sort_complete()
        assert sm.snapshot().last_sort is WasteCategory.PET
        # 다음 cycle을 sort 전에 중단
        sm.begin_detection()
        sm.begin_capture()
        sm.photo_captured()
        if abort == "reset":
            sm.reset()
        else:
            sm.set_maintenance(True)
            sm.set_maintenance(False)
        assert sm.snapshot().last_sort is None  # 중단된 cycle은 결과 없음


def test_invalid_transition_raises() -> None:
    sm = StateMachine()
    with pytest.raises(InvalidTransition):
        sm.photo_captured()  # CAPTURING이 아님
