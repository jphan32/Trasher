"""상태 OLED — DisplaySnapshot 구성·레이트리밋·스피너(오케스트레이터) + 라벨 매핑(순수).

라이브 I2C는 Pi에서만 가능하나, 표시 데이터·갱신 정책은 MockDisplay + FakeClock으로 결정적 검증.
luma 렌더 자체(픽셀)는 실기기 육안 검증 대상(여기선 비검증).
"""

from __future__ import annotations

from trash_sorter.app import _DISPLAY_MAX_FAILS, Orchestrator
from trash_sorter.ble import MockBleServer
from trash_sorter.config import Settings
from trash_sorter.hardware import MockDisplay
from trash_sorter.hardware.display import DisplaySnapshot, StatusDisplay, _state_label
from trash_sorter.hardware.mock import MockHardware
from trash_sorter.protocol import Command, CommandType, ErrorCode, PiState
from trash_sorter.state import StateMachine
from trash_sorter.vision import MockCamera, MotionDetector
from trash_sorter.vision.mock import blank
from trash_sorter.web.photo_server import PhotoStore

MIN_INTERVAL = 0.5  # DisplayConfig.min_interval_s 기본


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def _snap(state: PiState, *, started: bool = False) -> DisplaySnapshot:
    return DisplaySnapshot(
        state=state, cycle=0, started=started, err=None, last_sort=None,
        ble_connected=False, ip="", name="sorter-01",
    )


# --- 순수 라벨 매핑 ----------------------------------------------------------


def test_state_label_idle_distinguishes_ready_paused() -> None:
    assert _state_label(_snap(PiState.IDLE, started=True)) == "READY"
    assert _state_label(_snap(PiState.IDLE, started=False)) == "PAUSED"


def test_state_label_maps_known_states() -> None:
    assert _state_label(_snap(PiState.SORTING)) == "SORTING"
    assert _state_label(_snap(PiState.AWAITING_RESULT)) == "WAIT AI"
    assert _state_label(_snap(PiState.ERROR)) == "ERROR"
    assert _state_label(_snap(PiState.MAINTENANCE)) == "MAINT"


def test_mock_display_records_frames_and_spinner() -> None:
    disp = MockDisplay()
    s = _snap(PiState.IDLE)
    disp.render(s, spinner=2)
    assert disp.frames == [s]
    assert disp.spinners == [2]
    disp.close()
    assert disp.closed is True


# --- 오케스트레이터 통합 -----------------------------------------------------


def _build(tmp_path):
    clock = FakeClock()
    ble = MockBleServer()
    hw = MockHardware()
    disp = MockDisplay()
    orch = Orchestrator(
        settings=Settings(),
        state=StateMachine(),
        camera=MockCamera(frames=[blank(0)] * 50),
        motion=MotionDetector(threshold=0.02),
        hardware=hw,
        ble=ble,
        store=PhotoStore(tmp_path / "photos"),
        clock=clock,
        sleep=lambda _s: None,
        display=disp,
    )
    return orch, ble, disp, clock


def test_first_tick_renders_initial_state(tmp_path) -> None:
    orch, _ble, disp, _clock = _build(tmp_path)
    orch.tick()
    assert len(disp.frames) == 1
    f = disp.frames[0]
    assert f.state is PiState.IDLE
    assert f.started is False
    assert f.ble_connected is False
    assert f.name == "sorter-01"


def test_unchanged_within_interval_is_throttled(tmp_path) -> None:
    orch, _ble, disp, clock = _build(tmp_path)
    orch.tick()                 # 최초 렌더
    for _ in range(5):          # 클락 정지 → 변화 없음 → 추가 렌더 없음
        orch.tick()
    assert len(disp.frames) == 1
    clock.advance(MIN_INTERVAL + 0.01)
    orch.tick()                 # 간격 경과 → 스피너 갱신 렌더
    assert len(disp.frames) == 2
    assert disp.spinners[0] != disp.spinners[1]  # 스피너 전진(살아있음)


def test_state_change_renders_immediately(tmp_path) -> None:
    orch, ble, disp, _clock = _build(tmp_path)
    orch.tick()                 # idle 렌더
    n = len(disp.frames)
    ble.simulate_command(Command(cmd=CommandType.START, id=1))
    orch.tick()                 # START → started True + ble_connected True → 즉시 렌더(간격 무시)
    assert len(disp.frames) == n + 1
    f = disp.frames[-1]
    assert f.started is True
    assert f.ble_connected is True


def test_error_shown_on_snapshot(tmp_path) -> None:
    orch, ble, disp, _clock = _build(tmp_path)
    ble.simulate_command(Command(cmd=CommandType.ESTOP, id=2))
    orch.tick()
    f = disp.frames[-1]
    assert f.state is PiState.ERROR
    assert f.err is ErrorCode.ESTOPPED


def test_set_device_info_reflected_in_header(tmp_path) -> None:
    orch, _ble, disp, _clock = _build(tmp_path)
    orch.set_device_info(ip="192.168.0.50", name="sorter-09")
    orch.tick()
    f = disp.frames[-1]
    assert f.ip == "192.168.0.50"
    assert f.name == "sorter-09"


class _RaisingDisplay(StatusDisplay):
    """렌더 시 항상 예외(플레이키 I2C 모사). 시도 횟수를 센다."""

    def __init__(self) -> None:
        self.attempts = 0

    def render(self, snapshot: DisplaySnapshot, *, spinner: int = 0) -> None:
        self.attempts += 1
        raise OSError("i2c nack")

    def close(self) -> None:
        pass


def test_render_failure_is_rate_limited_then_disabled(tmp_path) -> None:
    clock = FakeClock()
    ble = MockBleServer()
    disp = _RaisingDisplay()
    orch = Orchestrator(
        settings=Settings(),
        state=StateMachine(),
        camera=MockCamera(frames=[blank(0)] * 50),
        motion=MotionDetector(threshold=0.02),
        hardware=MockHardware(),
        ble=ble,
        store=PhotoStore(tmp_path / "photos"),
        clock=clock,
        sleep=lambda _s: None,
        display=disp,
    )
    orch.tick()                       # 1회 시도(실패) — 레이트리밋 기준 갱신
    assert disp.attempts == 1
    for _ in range(5):                # 클락 정지 → 실패에도 레이트리밋 적용(추가 시도 없음)
        orch.tick()
    assert disp.attempts == 1
    for _ in range(10):               # min_interval마다 1회 재시도 → 연속 실패로 비활성화
        clock.advance(MIN_INTERVAL + 0.01)
        orch.tick()
    assert disp.attempts == _DISPLAY_MAX_FAILS  # disable latch에서 멈춤
    assert orch._display is None  # noqa: SLF001
