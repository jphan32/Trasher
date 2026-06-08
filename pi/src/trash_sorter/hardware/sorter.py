"""분류 이동 시퀀스 (시간 기반 완료). docs/protocol.md §2.5.

게이트 홀드 → 결과대로 분기 설정 → 게이트 열어 방출 → 벨트 T초 구동 → 정지·복귀.
``sleep`` 주입으로 테스트에서 시간을 건너뛴다.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from ..config import ROUTE_MAP, Settings
from ..protocol import WasteCategory
from .base import HardwareController


class Sorter:
    def __init__(
        self,
        hardware: HardwareController,
        settings: Settings,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._hw = hardware
        self._settings = settings
        self._sleep = sleep

    def hold(self) -> None:
        """캡처 동안 투입물을 캡처 존에 홀드(게이트 닫힘)."""
        self._hw.set_gate(open=False)
        self._hw.set_route("center")

    def begin_sort(self, category: WasteCategory) -> None:
        """§2.5 1~3단계: 분기 설정 → 게이트 방출 → 벨트 구동(논블로킹)."""
        self._hw.set_route(ROUTE_MAP[category])  # 1. 분기 경로 설정
        self._hw.set_gate(open=True)             # 2. 게이트 열어 방출
        self._hw.belt(on=True)                   # 3. 벨트 구동

    def finish_sort(self) -> None:
        """§2.5 5단계: 벨트 정지 → 게이트 홀드 → 분기 중앙 복귀."""
        self._hw.belt(on=False)
        self._hw.set_gate(open=False)
        self._hw.set_route("center")

    def sort(self, category: WasteCategory) -> None:
        """블로킹 전체 시퀀스(수동 SORT 명령/진단용). 벨트 구동을 sleep으로 대기."""
        self.begin_sort(category)
        self._sleep(self._settings.belt.run_seconds)  # 4. T_belt 대기
        self.finish_sort()
