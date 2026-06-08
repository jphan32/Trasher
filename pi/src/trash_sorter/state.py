"""상태 머신 (Pi 소유). docs/protocol.md §2.

순수 로직: 하드웨어·타이머·스레드 비의존. 타이밍은 오케스트레이터(app.py)가 구동하고,
이 클래스는 전이 규칙·cycle·seq만 책임진다. 매 ``snapshot()`` 호출 시 seq를 증가시킨다.
"""

from __future__ import annotations

from .protocol import ErrorCode, PiState, Status, WasteCategory


class InvalidTransition(RuntimeError):
    """현재 상태에서 허용되지 않는 전이를 호출했을 때."""


class StateMachine:
    def __init__(self) -> None:
        self._state = PiState.IDLE
        self._cycle = 0
        self._seq = 0
        self._err: ErrorCode | None = None
        self._last_sort: WasteCategory | None = None
        self._started = False  # §2.1 게이팅: iPad의 start 전까지 감지 안 함
        self._pending_sort: WasteCategory | None = None

    # --- 조회 ---------------------------------------------------------------
    @property
    def state(self) -> PiState:
        return self._state

    @property
    def cycle(self) -> int:
        return self._cycle

    @property
    def started(self) -> bool:
        return self._started

    @property
    def pending_sort(self) -> WasteCategory | None:
        """sorting 진입 시 구동할 카테고리(오케스트레이터가 읽음)."""
        return self._pending_sort

    def snapshot(self) -> Status:
        """현재 상태의 Status 페이로드. 하트비트로 호출될 때마다 seq +1."""
        self._seq += 1
        return Status(
            state=self._state,
            cycle=self._cycle,
            seq=self._seq,
            err=self._err,
            last_sort=self._last_sort,
        )

    # --- §2.1 게이팅 (start/stop) ------------------------------------------
    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        # 새 사이클 감지만 멈춘다. 진행 중 사이클은 그대로 완료.
        self._started = False

    # --- 정상 사이클 전이 ---------------------------------------------------
    def begin_detection(self) -> bool:
        """변이 감지 시작. started이고 idle일 때만 수락. 새 cycle 할당."""
        if not self._started or self._state is not PiState.IDLE:
            return False
        self._cycle += 1
        self._err = None
        self._state = PiState.DETECTING
        return True

    def begin_capture(self) -> None:
        self._require(PiState.DETECTING)
        self._state = PiState.CAPTURING

    def photo_captured(self) -> int:
        """사진 촬영 완료 → 결과 대기. 현재 cycle 반환."""
        self._require(PiState.CAPTURING)
        self._state = PiState.AWAITING_RESULT
        return self._cycle

    def result(self, cycle: int, category: WasteCategory) -> bool:
        """iPad 분류 결과 수신. cycle 불일치(오래된 결과)면 폐기(False)."""
        if self._state is not PiState.AWAITING_RESULT:
            return False
        if cycle != self._cycle:
            return False
        self._enter_sorting(category)
        return True

    def result_timeout(self) -> None:
        """§6 결과 타임아웃 → other로 자체 처리."""
        self._require(PiState.AWAITING_RESULT)
        self._err = ErrorCode.RESULT_TIMEOUT
        self._enter_sorting(WasteCategory.OTHER)

    def sort_complete(self) -> None:
        self._require(PiState.SORTING)
        self._pending_sort = None
        self._state = PiState.IDLE

    # --- 제어/예외 전이 -----------------------------------------------------
    def reset(self) -> None:
        """현재 사이클 중단 → idle."""
        self._pending_sort = None
        self._err = None
        self._state = PiState.IDLE

    def estop(self) -> None:
        self.fault(ErrorCode.ESTOPPED)

    def fault(self, code: ErrorCode) -> None:
        self._err = code
        self._pending_sort = None
        self._state = PiState.ERROR

    def set_maintenance(self, on: bool) -> None:
        if on:
            self._pending_sort = None
            self._state = PiState.MAINTENANCE
        elif self._state is PiState.MAINTENANCE:
            self._state = PiState.IDLE

    # --- 내부 --------------------------------------------------------------
    def _enter_sorting(self, category: WasteCategory) -> None:
        self._pending_sort = category
        self._last_sort = category  # §2.2 정합화: Status.lastSort로 노출
        self._state = PiState.SORTING

    def _require(self, expected: PiState) -> None:
        if self._state is not expected:
            raise InvalidTransition(f"expected {expected.value}, got {self._state.value}")
