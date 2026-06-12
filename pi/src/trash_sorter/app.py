"""오케스트레이터: 상태머신·비전·하드웨어·BLE·HTTP를 결선하고 분류 사이클을 구동.

docs/protocol.md §2(상태머신), §2.1(게이팅), §2.5(sort), §6(타임아웃 폴백).

스레딩: BLE write(on_command/on_result)는 BLE 스레드에서 도착 → 스레드세이프 Queue로 받고,
메인 루프(tick)에서 처리한다. 시간은 ``clock``/``sleep`` 주입으로 테스트에서 결정적으로 제어.
"""

from __future__ import annotations

import logging
import queue
import time
from collections.abc import Callable

from .ble.base import BleServer
from .config import Settings
from .hardware.base import HardwareController
from .hardware.button import ButtonEvent, ButtonInput, PressDetector
from .hardware.display import DisplaySnapshot, StatusDisplay
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

log = logging.getLogger(__name__)

# 디스플레이 렌더가 연속 N회 실패하면(예: 운영 중 OLED 탈락) 비활성화해 로그 스팸·루프 지연 방지.
_DISPLAY_MAX_FAILS = 5


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
        button: ButtonInput | None = None,
        display: StatusDisplay | None = None,
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
        self._last_motion: float | None = None  # DETECTING 중 마지막 변이 시각(정지 판정 기준)
        self._awaiting_since: float | None = None
        self._sort_since: float | None = None  # 논블로킹 사이클 sorting 타이밍
        self._manual_sort_since: float | None = None  # 논블로킹 수동(진단) sort 타이밍
        self._last_heartbeat = 0.0
        self._running = False

        # 물리 리셋 버튼(옵션) — None이면 폴링 no-op. PressDetector는 항상 두되 입력만 없을 뿐.
        self._button = button
        self._press = PressDetector(
            debounce_s=settings.button.debounce_s, long_press_s=settings.button.long_press_s
        )
        # 상태 OLED(옵션) — None이면 렌더 no-op. 레이트리밋·스피너·연속실패 카운트.
        self._display = display
        self._last_display_snap: DisplaySnapshot | None = None
        self._last_display_at = float("-inf")
        self._spinner = 0
        self._display_fails = 0
        # OLED 헤더에 표시할 장치 식별자(IP는 HTTP 시작 후 set_device_info로 갱신).
        self._dev_ip = settings.network.advertised_ip
        self._dev_name = settings.device_name
        # Central(iPad) 연결 추정 — connect 훅이 없어 inbound 트래픽/disconnect로 best-effort 추적.
        self._central_active = False

    # --- 생명주기 ----------------------------------------------------------
    def run(self, poll_interval: float = 0.02) -> None:  # pragma: no cover - 무한루프
        self._running = True
        while self._running:
            self.tick()
            self._sleep(poll_interval)

    def stop_running(self) -> None:
        self._running = False

    def set_device_info(self, *, ip: str, name: str) -> None:
        """OLED 헤더에 표시할 장치 IP/이름 갱신. __main__이 HTTP 시작 후(IP 확정) 1회 호출."""
        self._dev_ip = ip
        self._dev_name = name

    # --- 한 사이클 반복 -----------------------------------------------------
    def tick(self) -> None:
        self._drain_disconnects()
        self._drain_commands()
        self._drain_results()
        self._poll_button()  # 물리 리셋 버튼(항상 오버라이드) — 상태 전개 전에 처리
        self._advance_manual_sort()
        self._advance_state()
        self._maybe_heartbeat()
        self._update_display()  # 마지막: 이 tick의 최종 상태를 반영

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

    # --- 물리 리셋 버튼 ------------------------------------------------------
    def _poll_button(self) -> None:
        """매 tick 버튼 raw 상태를 읽어 디바운스·짧게/길게 판정 → 이벤트 처리. 버튼 없으면 no-op."""
        if self._button is None:
            return
        event = self._press.update(self._button.is_pressed(), self._clock())
        if event is not None:
            self._handle_button(event)

    def _handle_button(self, event: ButtonEvent) -> None:
        """리셋 버튼 처리 — **항상(오버라이드)**: 어느 상태든 진행 정지 → 서보 홈 → idle.

        짧게(SHORT)=detach-홈(현재 위치를 홈으로), 길게(LONG)=타이머 재시팅(하드스톱 복귀).
        E-STOP과 별개의 정비/캘리브레이션용 물리 버튼이라 ERROR/MAINTENANCE/사이클 중에도 동작한다.
        """
        self._abort_active_sort()  # 진행 중 벨트/서보 즉시 정지(있을 때만 stop_all)
        self._hw.home(reseat=(event is ButtonEvent.LONG))
        self._sm.reset()  # → idle (started 유지 — RESET 명령과 동일 시맨틱)
        self._reset_timers()
        kind = "재시팅" if event is ButtonEvent.LONG else "detach"
        log.info("리셋 버튼: %s → 서보 홈(%s)", event.value, kind)
        self._publish_status()

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
        self._central_active = False  # OLED 연결 표시 갱신
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
            self._central_active = True  # iPad가 결과를 보냄 → 연결 중(OLED 표시)
            if self._sm.result(res.cycle, res.category):  # cycle 불일치는 폐기
                self._publish_status()

    def _handle_command(self, cmd: Command) -> None:
        self._central_active = True  # iPad가 명령을 보냄 → 연결 중(OLED 표시)
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
                    # 잘못된 카테고리·비-IDLE·중복은 '거부'(ok=False, err=None) — 내부오류 아님(m6).
                    valid = self._require_arg(cmd.arg, tuple(c.value for c in WasteCategory))
                    if valid and self._sm.state is PiState.IDLE and self._manual_sort_since is None:
                        self._sorter.begin_sort(WasteCategory((cmd.arg or "").lower()))
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
        # 검증 실패(잘못된 arg·비-IDLE sort 등)는 err=None으로 두어 '거부'를 '내부 오류'와 구분한다.
        # 진짜 내부 예외만 ErrorCode.INTERNAL(except 블록)로 표기. (CommandAck.err은 optional)
        self._ble.publish_command_ack(CommandAck(id=cmd.id, ok=ok, err=err))
        self._publish_status()

    @staticmethod
    def _require_arg(arg: str | None, allowed: tuple[str, ...]) -> bool:
        # isinstance로 비-문자열 arg(잘못된 JSON boolean 등) AttributeError 방지 → ok=False.
        return isinstance(arg, str) and arg.lower() in allowed

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
                self._last_motion = self._clock()  # 방금 변이 감지 → 정지 타이머 기준
                self._publish_status()

    def _maybe_capture(self) -> None:
        # 움직임이 멎고 settle_seconds 동안 정지면 촬영. docs/protocol.md §"카메라 캡처".
        # 감지는 OK지만 움직이는 중 촬영하면 흔들리므로, 정지 확인 후 촬영한다.
        frame = self._cam.read_frame()
        now = self._clock()
        if self._detect_since is None:
            self._detect_since = now
        if self._last_motion is None:
            self._last_motion = now
        if self._motion.is_motion(frame):
            self._last_motion = now  # 아직 움직임 → 정지 타이머 리셋(계속 대기)
        settled = now - self._last_motion >= self._s.vision.settle_seconds
        overdue = now - self._detect_since >= self._s.vision.detect_max_seconds  # 무한대기 방지
        if not settled and not overdue:
            return  # 정지(또는 최대 대기) 전 — 촬영 보류
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
        self._last_motion = None
        self._awaiting_since = None

    # --- 출력 --------------------------------------------------------------
    def _publish_status(self) -> None:
        self._ble.publish_status(self._sm.snapshot())
        self._last_heartbeat = self._clock()

    def _maybe_heartbeat(self) -> None:
        if self._clock() - self._last_heartbeat >= self._s.timing.heartbeat_period_s:
            self._publish_status()

    # --- 상태 OLED ----------------------------------------------------------
    def _build_display_snapshot(self) -> DisplaySnapshot:
        """현재 상태를 OLED 프레임으로. seq를 올리지 않는 조회만 사용(snapshot() 부작용 회피)."""
        return DisplaySnapshot(
            state=self._sm.state,
            cycle=self._sm.cycle,
            started=self._sm.started,
            err=self._sm.err,
            last_sort=self._sm.last_sort,
            ble_connected=self._central_active,
            ip=self._dev_ip,
            name=self._dev_name,
        )

    def _update_display(self) -> None:
        """OLED 갱신. 상태 변화는 즉시, 무변화 시 min_interval마다 그린다(스피너·I2C 보호)."""
        if self._display is None:
            return
        now = self._clock()
        snap = self._build_display_snapshot()
        changed = snap != self._last_display_snap
        due = now - self._last_display_at >= self._s.display.min_interval_s
        if not changed and not due:
            return
        self._spinner = (self._spinner + 1) & 3
        # 성공·실패 무관하게 레이트리밋 기준(snap/at)을 먼저 갱신 — 실패해도 다음 tick에 즉시
        # 재시도하지 않도록(I2C 트래픽 보호). 다음 시도는 min_interval 경과 후.
        self._last_display_snap = snap
        self._last_display_at = now
        try:
            self._display.render(snap, spinner=self._spinner)
            self._display_fails = 0
        except Exception as e:  # noqa: BLE001 - 디스플레이 오류는 비치명(루프 계속)
            self._display_fails += 1
            if self._display_fails >= _DISPLAY_MAX_FAILS:
                log.warning("OLED 렌더 %d회 연속 실패 — 비활성화: %s", self._display_fails, e)
                self._display = None


def _truthy(arg: str | None) -> bool:
    return str(arg).lower() in ("true", "1", "on", "yes")
