"""오케스트레이터: 상태머신·비전·하드웨어·BLE·HTTP를 결선하고 분류 사이클을 구동.

docs/protocol.md §2(상태머신), §2.1(게이팅), §2.5(sort), §6(타임아웃 폴백).

스레딩: BLE write(on_command/on_result)는 BLE 스레드에서 도착 → 스레드세이프 Queue로 받고,
메인 루프(tick)에서 처리한다. 시간은 ``clock``/``sleep`` 주입으로 테스트에서 결정적으로 제어.
"""

from __future__ import annotations

import queue
import time
from collections.abc import Callable

from .ble.base import BleServer
from .config import Settings
from .hardware.base import HardwareController
from .hardware.sorter import Sorter
from .protocol import (
    ClassificationResult,
    Command,
    CommandAck,
    CommandType,
    ErrorCode,
    PhotoReady,
    PiState,
    WasteCategory,
)
from .state import StateMachine
from .vision.base import Camera
from .vision.motion import MotionDetector
from .web.photo_server import PhotoStore


class Orchestrator:
    def __init__(
        self,
        settings: Settings,
        state: StateMachine,
        camera: Camera,
        motion: MotionDetector,
        hardware: HardwareController,
        ble: BleServer,
        store: PhotoStore,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._s = settings
        self._sm = state
        self._cam = camera
        self._motion = motion
        self._hw = hardware
        self._sorter = Sorter(hardware, settings, sleep=sleep)
        self._ble = ble
        self._store = store
        self._clock = clock
        self._sleep = sleep

        self._cmds: queue.Queue[Command] = queue.Queue()
        self._results: queue.Queue[ClassificationResult] = queue.Queue()
        self._disconnects: queue.Queue[bool] = queue.Queue()
        ble.on_command = self._cmds.put
        ble.on_result = self._results.put
        ble.on_disconnect = lambda: self._disconnects.put(True)

        self._detect_since: float | None = None
        self._awaiting_since: float | None = None
        self._sort_since: float | None = None  # 논블로킹 사이클 sorting 타이밍
        self._manual_sort_since: float | None = None  # 논블로킹 수동(진단) sort 타이밍
        self._last_heartbeat = 0.0
        self._running = False

    # --- 생명주기 ----------------------------------------------------------
    def run(self, poll_interval: float = 0.02) -> None:  # pragma: no cover - 무한루프
        self._running = True
        while self._running:
            self.tick()
            self._sleep(poll_interval)

    def stop_running(self) -> None:
        self._running = False

    # --- 한 사이클 반복 -----------------------------------------------------
    def tick(self) -> None:
        self._drain_disconnects()
        self._drain_commands()
        self._drain_results()
        self._advance_manual_sort()
        self._advance_state()
        self._maybe_heartbeat()

    def _advance_manual_sort(self) -> None:
        """논블로킹 수동 SORT: T_belt 경과 시 finish. 루프를 막지 않아 estop이 매 tick 처리됨."""
        if self._manual_sort_since is None:
            return
        if self._clock() - self._manual_sort_since >= self._s.belt.run_seconds:
            self._sorter.finish_sort()
            self._manual_sort_since = None

    def _abort_active_sort(self) -> None:
        """진행 중 sort(사이클/수동)를 안전 정지. RESET/MAINTENANCE/disconnect의 비상 외 중단 경로.

        벨트가 켜진 상태로 SORTING을 벗어나면 finish_sort가 호출되지 않아 벨트가 멈추지 않으므로,
        하드웨어를 즉시 정지(stop_all)하고 타이머를 정리한다.
        """
        if self._sort_since is not None or self._manual_sort_since is not None:
            self._hw.stop_all()
        self._sort_since = None
        self._manual_sort_since = None

    def _drain_disconnects(self) -> None:
        had = False
        while True:
            try:
                self._disconnects.get_nowait()
                had = True
            except queue.Empty:
                break
        if had:
            self._handle_disconnect()

    def _handle_disconnect(self) -> None:
        """§6 BLE 끊김: 진행 중 사이클을 안전 정리. iPad 재연결 시 start로 재개."""
        self._hw.stop_all()
        self._sort_since = None
        self._manual_sort_since = None
        self._sm.reset()
        self._sm.stop()  # iPad가 다시 start 보낼 때까지 감지 중단
        self._reset_timers()

    # --- 입력 처리 ----------------------------------------------------------
    def _drain_commands(self) -> None:
        while True:
            try:
                cmd = self._cmds.get_nowait()
            except queue.Empty:
                return
            self._handle_command(cmd)

    def _drain_results(self) -> None:
        while True:
            try:
                res = self._results.get_nowait()
            except queue.Empty:
                return
            if self._sm.result(res.cycle, res.category):  # cycle 불일치는 폐기
                self._publish_status()

    def _handle_command(self, cmd: Command) -> None:
        ok = True
        err: ErrorCode | None = None
        try:
            match cmd.cmd:
                case CommandType.START:
                    self._sm.start()
                case CommandType.STOP:
                    self._sm.stop()
                case CommandType.RESET:
                    self._abort_active_sort()  # 진행 중 벨트 정지
                    self._sm.reset()
                case CommandType.ESTOP:
                    self._sort_since = None
                    self._manual_sort_since = None
                    self._hw.stop_all()
                    self._sm.estop()
                case CommandType.MAINTENANCE:
                    ok = self._require_arg(cmd.arg, ("true", "false", "1", "0", "on", "off"))
                    if ok:
                        if _truthy(cmd.arg):
                            self._abort_active_sort()  # 점검 진입 전 벨트 정지
                        self._sm.set_maintenance(_truthy(cmd.arg))
                case CommandType.SORT:
                    # 비-블로킹 진단 sort: begin 후 tick에서 T_belt 경과 시 finish.
                    # IDLE에서만, 중복 금지. 잘못된 arg는 WasteCategory()가 ValueError→ok=False.
                    cat = WasteCategory(cmd.arg or "")
                    if self._sm.state is PiState.IDLE and self._manual_sort_since is None:
                        self._sorter.begin_sort(cat)
                        self._manual_sort_since = self._clock()
                    else:
                        ok = False
                case CommandType.BELT:
                    ok = self._require_arg(cmd.arg, ("fwd", "stop"))
                    if ok:
                        self._hw.belt(on=(cmd.arg == "fwd"))
                case CommandType.CALIBRATE:
                    pass  # 스캐폴드: no-op
        except (ValueError, KeyError):
            ok, err = False, ErrorCode.INTERNAL
        if not ok and err is None:
            err = ErrorCode.INTERNAL
        self._ble.publish_command_ack(CommandAck(id=cmd.id, ok=ok, err=err))
        self._publish_status()

    @staticmethod
    def _require_arg(arg: str | None, allowed: tuple[str, ...]) -> bool:
        return arg is not None and arg.lower() in allowed

    # --- 상태 전개 ----------------------------------------------------------
    def _advance_state(self) -> None:
        state = self._sm.state
        if state is PiState.IDLE:
            self._maybe_begin_detection()
        elif state is PiState.DETECTING:
            self._maybe_capture()
        elif state is PiState.AWAITING_RESULT:
            self._maybe_timeout()
        elif state is PiState.SORTING:
            self._run_sort()

    def _maybe_begin_detection(self) -> None:
        if not self._sm.started or self._manual_sort_since is not None:
            return  # 수동 진단 sort 중에는 감지하지 않는다
        if self._motion.is_motion(self._cam.read_frame()):
            if self._sm.begin_detection():
                self._detect_since = self._clock()
                self._publish_status()

    def _maybe_capture(self) -> None:
        # 안정화(settle) 시간 경과 후 촬영. docs/protocol.md §"카메라 캡처".
        self._cam.read_frame()  # 스트림 유지
        if self._detect_since is None:
            self._detect_since = self._clock()
        if self._clock() - self._detect_since < self._s.vision.settle_seconds:
            return
        self._sorter.hold()  # 게이트 닫아 캡처 존 홀드
        self._sm.begin_capture()
        cycle = self._sm.cycle
        path = self._store.path_for(cycle)
        try:
            w, h = self._cam.capture_photo(str(path))
        except Exception:  # noqa: BLE001 - 캡처 실패는 camera_fail로 전환
            self._fault(ErrorCode.CAMERA_FAIL)
            return
        self._store.prune()
        self._sm.photo_captured()
        self._awaiting_since = self._clock()
        self._ble.publish_photo_ready(
            PhotoReady(cycle=cycle, path=self._store.url_path(cycle), w=w, h=h)
        )
        self._publish_status()

    def _maybe_timeout(self) -> None:
        if self._awaiting_since is None:
            self._awaiting_since = self._clock()
        if self._clock() - self._awaiting_since >= self._s.timing.result_timeout_s:
            self._sm.result_timeout()  # → sorting(other)
            self._publish_status()

    def _run_sort(self) -> None:
        """논블로킹 sorting: 시작(begin) 후 T_belt 경과 시 종료(finish). 루프 응답성 유지."""
        category = self._sm.pending_sort or WasteCategory.OTHER
        if self._sort_since is None:
            try:
                self._sorter.begin_sort(category)
            except Exception:  # noqa: BLE001 - 모터 실패는 motor_fail로 전환
                self._fault(ErrorCode.MOTOR_FAIL)
                return
            self._sort_since = self._clock()
            return
        if self._clock() - self._sort_since < self._s.belt.run_seconds:
            return  # 벨트 구동 중 — estop/reset은 매 tick 처리됨
        try:
            self._sorter.finish_sort()
        except Exception:  # noqa: BLE001
            self._fault(ErrorCode.MOTOR_FAIL)
            return
        self._sort_since = None
        self._sm.sort_complete()
        self._reset_timers()
        self._motion.reset()
        self._publish_status()

    def _fault(self, code: ErrorCode) -> None:
        self._hw.stop_all()
        self._sort_since = None
        self._sm.fault(code)
        self._reset_timers()
        self._publish_status()

    def _reset_timers(self) -> None:
        self._detect_since = None
        self._awaiting_since = None

    # --- 출력 --------------------------------------------------------------
    def _publish_status(self) -> None:
        self._ble.publish_status(self._sm.snapshot())
        self._last_heartbeat = self._clock()

    def _maybe_heartbeat(self) -> None:
        if self._clock() - self._last_heartbeat >= self._s.timing.heartbeat_period_s:
            self._publish_status()


def _truthy(arg: str | None) -> bool:
    return str(arg).lower() in ("true", "1", "on", "yes")
