"""sort 시퀀스 + 카테고리→경로 매핑 테스트. docs/protocol.md §2.5."""

from __future__ import annotations

import pytest

from trash_sorter.config import Settings
from trash_sorter.hardware import MockHardware, Sorter
from trash_sorter.protocol import WasteCategory


def _sorter() -> tuple[Sorter, MockHardware]:
    hw = MockHardware()
    slept: list[float] = []
    sorter = Sorter(hw, Settings(), sleep=slept.append)
    return sorter, hw


@pytest.mark.parametrize(
    "category,route",
    [(WasteCategory.PET, "left"), (WasteCategory.CAN, "right"), (WasteCategory.OTHER, "center")],
)
def test_sort_routes(category: WasteCategory, route: str) -> None:
    sorter, hw = _sorter()
    sorter.sort(category)
    # 분기 경로가 카테고리 매핑대로 설정됐는지(중앙 복귀 전에 최소 1회)
    assert f"route:{route}" in hw.calls
    # 완료 후 중립 복귀
    assert hw.calls[-1] == "route:center"
    assert hw.gate_open is False
    assert hw.belt_on is False


def test_sort_sequence_order() -> None:
    sorter, hw = _sorter()
    sorter.sort(WasteCategory.PET)
    assert hw.calls == [
        "route:left",   # 1. 분기 설정
        "gate:open",    # 2. 방출
        "belt:on",      # 3. 벨트 구동
        "belt:off",     # 5. 정지
        "gate:closed",  #    홀드 복귀
        "route:center",  #   중앙 복귀
    ]


def test_hold_for_capture() -> None:
    sorter, hw = _sorter()
    sorter.hold()
    assert hw.gate_open is False
    assert hw.route == "center"
