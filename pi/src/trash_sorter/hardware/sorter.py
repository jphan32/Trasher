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

    def sort(self, category: WasteCategory) -> None:
        """§2.5 sorting 시퀀스. 완료 시 중립(게이트 닫힘·중앙)으로 복귀."""
        route = ROUTE_MAP[category]
        self._hw.set_route(route)        # 1. 분기 경로 설정
        self._hw.set_gate(open=True)     # 2. 게이트 열어 방출
        self._hw.belt(on=True)           # 3. 벨트 구동
        self._sleep(self._settings.belt.run_seconds)  # 4. T_belt 대기
        self._hw.belt(on=False)          # 5. 벨트 정지
        self._hw.set_gate(open=False)    #    게이트 닫힘(홀드 복귀)
        self._hw.set_route("center")     #    분기 중앙(닫힘) 복귀
