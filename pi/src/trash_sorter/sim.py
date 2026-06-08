"""시뮬레이션 모드 — 하드웨어 없이 전 사이클을 구동(로깅/타이밍 검증·QA).

모의 모션 프레임을 카메라에 흘리고, 가짜 iPad가 PhotoReady에 자동으로 분류 결과를 응답한다.
실기기/실 BLE/실 iPad 없이 Pi 오케스트레이터의 동작과 로그를 점검할 수 있다.

실행: `trash-sorter --simulate` (또는 `python -m trash_sorter --simulate`).
"""

from __future__ import annotations

import itertools
import logging
import tempfile
import time
from collections.abc import Callable, Iterator

from .app import Orchestrator
from .ble.mock import MockBleServer
from .config import Settings, load_settings
from .hardware.mock import MockHardware
from .protocol import ClassificationResult, Command, CommandType, WasteCategory
from .state import StateMachine
from .vision.base import Frame
from .vision.mock import MockCamera, blank
from .vision.motion import MotionDetector
from .web.photo_server import PhotoStore


def sim_frames() -> Iterator[Frame]:
    """모션 펄스가 반복되는 무한 프레임 스트림(blank↔bright 전환이 모션을 유발)."""
    while True:
        yield blank(0)
        yield blank(0)
        yield blank(255)  # 변화 → 모션 감지
        for _ in range(30):
            yield blank(255)  # 정지(안정화 동안)
        yield blank(0)
        yield blank(0)


class Simulation:
    def __init__(
        self,
        settings: Settings | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        settings = settings or load_settings()
        self.ble = MockBleServer()
        self.hw = MockHardware()
        self.store = PhotoStore(
            tempfile.mkdtemp(prefix="trash-sim-"), retention=settings.network.photo_retention
        )
        self.orchestrator = Orchestrator(
            settings=settings,
            state=StateMachine(),
            camera=MockCamera(frames=sim_frames()),
            motion=MotionDetector(threshold=settings.vision.motion_threshold),
            hardware=self.hw,
            ble=self.ble,
            store=self.store,
            clock=clock,
            sleep=sleep,
        )
        self._categories = itertools.cycle(
            [WasteCategory.PET, WasteCategory.CAN, WasteCategory.OTHER]
        )
        self._answered = 0
        self.ble.simulate_command(Command(cmd=CommandType.START, id=0))  # 자동 시작

    def tick(self) -> None:
        self.orchestrator.tick()
        self._auto_respond()

    def _auto_respond(self) -> None:
        """새 PhotoReady마다 가짜 iPad가 분류 결과를 회신(카테고리 회전)."""
        while self._answered < len(self.ble.photos):
            photo = self.ble.photos[self._answered]
            self._answered += 1
            category = next(self._categories)
            self.ble.simulate_result(
                ClassificationResult(cycle=photo.cycle, category=category, confidence=0.9)
            )

    @property
    def cycles_completed(self) -> int:
        return self._answered

    def run(self, max_ticks: int | None = None, poll: float = 0.02) -> None:  # pragma: no cover
        log = logging.getLogger("trash_sorter.sim")
        last_state = None
        ticks = 0
        while max_ticks is None or ticks < max_ticks:
            self.tick()
            ticks += 1
            status = self.ble.last_status
            if status is not None and status.state != last_state:
                last_state = status.state
                log.info(
                    "state=%s cycle=%s lastSort=%s err=%s",
                    status.state.value,
                    status.cycle,
                    status.last_sort.value if status.last_sort else "-",
                    status.err.value if status.err else "-",
                )
            self.orchestrator._sleep(poll)  # noqa: SLF001 - 주입된 sleep
