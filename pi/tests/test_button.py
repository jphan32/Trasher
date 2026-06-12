"""물리 리셋 버튼 — PressDetector(디바운스·짧게/길게) 순수 로직 + 오케스트레이터 통합.

라이브 GPIO는 Pi에서만 가능하나, 판정 로직은 순수(clock 주입)라 macOS에서 결정적으로 검증한다
(벨트 fake-bus 테스트와 같은 '현재 가능한 수준'). 통합은 MockButton + FakeClock으로.
"""

from __future__ import annotations

from trash_sorter.app import Orchestrator
from trash_sorter.ble import MockBleServer
from trash_sorter.config import Settings
from trash_sorter.hardware import MockButton, PressDetector
from trash_sorter.hardware.button import ButtonEvent
from trash_sorter.hardware.mock import MockHardware
from trash_sorter.protocol import Command, CommandType, PiState, WasteCategory
from trash_sorter.state import StateMachine
from trash_sorter.vision import MockCamera, MotionDetector
from trash_sorter.vision.mock import blank
from trash_sorter.web.photo_server import PhotoStore

DEBOUNCE = 0.04
LONG = 0.8


# --- PressDetector 순수 로직 -------------------------------------------------


def _detector() -> PressDetector:
    return PressDetector(debounce_s=DEBOUNCE, long_press_s=LONG)


def _feed(det: PressDetector, samples: list[tuple[bool, float]]) -> list[ButtonEvent]:
    return [e for raw, t in samples if (e := det.update(raw, t)) is not None]


def test_clean_short_press_emits_single_short() -> None:
    det = _detector()
    events = _feed(
        det,
        [
            (False, 0.0),
            (True, 1.00),   # 눌림 후보
            (True, 1.06),   # 디바운스 경과 → 눌림 확정(이벤트 없음)
            (False, 1.20),  # 릴리스 후보
            (False, 1.26),  # 디바운스 경과 → 릴리스 확정 → SHORT
        ],
    )
    assert events == [ButtonEvent.SHORT]


def test_long_press_emits_single_long_and_no_short_on_release() -> None:
    det = _detector()
    events = _feed(
        det,
        [
            (True, 0.00),
            (True, 0.06),          # 눌림 확정
            (True, 0.06 + LONG),   # long 임계 도달 → LONG(릴리스 전 즉시)
            (True, 1.50),          # 계속 눌러도 추가 이벤트 없음
            (False, 2.00),
            (False, 2.06),         # 릴리스 — LONG 이미 냈으므로 SHORT 없음
        ],
    )
    assert events == [ButtonEvent.LONG]


def test_chatter_within_debounce_never_registers() -> None:
    # 디바운스 창보다 빠르게 토글(채터링)하면 논리 상태가 전이되지 않아 이벤트가 없다.
    det = _detector()
    chatter = [(bool(i % 2), 1.0 + i * 0.01) for i in range(1, 9)]  # 0.01s 간격 < 0.04
    assert _feed(det, chatter) == []
    # 채터링이 멎고 안정되게 눌리면 그제서야 눌림 확정(이후 릴리스로 SHORT).
    stable = [(True, 1.20), (True, 1.30), (False, 1.50), (False, 1.60)]
    assert _feed(det, stable) == [ButtonEvent.SHORT]


def test_release_bounce_does_not_double_fire() -> None:
    # 릴리스 직후 바운스가 튀어도 한 누름은 정확히 한 이벤트(SHORT)만.
    det = _detector()
    events = _feed(
        det,
        [
            (True, 0.0), (True, 0.06),            # 눌림 확정
            (False, 0.20), (False, 0.26),         # 릴리스 확정 → SHORT
            (True, 0.27), (False, 0.275),         # 바운스(디바운스 미달) → 무시
            (False, 0.40),
        ],
    )
    assert events == [ButtonEvent.SHORT]


def test_long_press_measured_from_physical_press_not_debounce() -> None:
    # long 임계는 물리 눌림(raw True 전이)부터 측정 — 디바운스 확정 시각 기준이면 0.75라 미발화.
    det = _detector()  # debounce 0.04, long 0.8
    events = _feed(
        det,
        [
            (True, 0.00),  # 물리 눌림
            (True, 0.05),  # 디바운스 확정(press_start=물리 눌림 0.00)
            (True, 0.80),  # 물리 눌림 후 정확히 long_press_s → LONG
        ],
    )
    assert events == [ButtonEvent.LONG]


def test_mock_button_reports_flag() -> None:
    btn = MockButton()
    assert btn.is_pressed() is False
    btn.pressed = True
    assert btn.is_pressed() is True


# --- 오케스트레이터 통합 -----------------------------------------------------


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def _build(tmp_path, *, run_seconds: float = 10.0):
    clock = FakeClock()
    ble = MockBleServer()
    hw = MockHardware()
    btn = MockButton()
    from trash_sorter.config import BeltConfig

    settings = Settings(belt=BeltConfig(run_seconds=run_seconds))
    orch = Orchestrator(
        settings=settings,
        state=StateMachine(),
        camera=MockCamera(frames=[blank(0)] * 50),
        motion=MotionDetector(threshold=0.02),
        hardware=hw,
        ble=ble,
        store=PhotoStore(tmp_path / "photos"),
        clock=clock,
        sleep=lambda _s: None,
        button=btn,
    )
    return orch, ble, hw, btn, clock


def _press(orch, btn, clock, *, hold: float) -> None:
    """버튼을 hold초 눌렀다 뗀다(디바운스를 넘기며 tick). 통합 경로 구동."""
    btn.pressed = True
    orch.tick()                 # 눌림 후보
    clock.advance(DEBOUNCE + 0.01)
    orch.tick()                 # 눌림 확정
    clock.advance(hold)
    orch.tick()                 # hold 경과(길게면 이 tick에서 LONG)
    btn.pressed = False
    orch.tick()                 # 릴리스 후보(last_change 기록)
    clock.advance(DEBOUNCE + 0.01)
    orch.tick()                 # 릴리스 확정(짧게면 여기서 SHORT)


def test_short_press_homes_detach_and_idles(tmp_path) -> None:
    orch, _ble, hw, btn, clock = _build(tmp_path)
    _press(orch, btn, clock, hold=0.1)  # < long_press → SHORT
    assert "home:detach" in hw.calls
    assert "home:reseat" not in hw.calls
    assert orch._sm.state is PiState.IDLE  # noqa: SLF001


def test_long_press_homes_reseat(tmp_path) -> None:
    orch, _ble, hw, btn, clock = _build(tmp_path)
    _press(orch, btn, clock, hold=LONG + 0.1)  # ≥ long_press → LONG
    assert "home:reseat" in hw.calls
    assert orch._sm.state is PiState.IDLE  # noqa: SLF001


def test_button_overrides_active_sort_stops_belt(tmp_path) -> None:
    # 항상-오버라이드: 수동 sort로 벨트가 켜진 상태에서 버튼 → 벨트 정지 + 홈 + idle.
    orch, ble, hw, btn, clock = _build(tmp_path, run_seconds=10.0)
    ble.simulate_command(Command(cmd=CommandType.SORT, id=1, arg=WasteCategory.PET.value))
    orch.tick()  # begin_sort → 벨트 ON
    assert hw.belt_on is True
    _press(orch, btn, clock, hold=0.1)
    assert hw.belt_on is False           # 진행 중 sort를 멈춤
    assert "stop_all" in hw.calls
    assert "home:detach" in hw.calls
    assert orch._sm.state is PiState.IDLE  # noqa: SLF001


def test_no_button_is_noop(tmp_path) -> None:
    # button=None이면 폴링이 no-op(회귀 안전: 기존 구성 그대로).
    clock = FakeClock()
    ble = MockBleServer()
    hw = MockHardware()
    orch = Orchestrator(
        settings=Settings(),
        state=StateMachine(),
        camera=MockCamera(frames=[blank(0)] * 5),
        motion=MotionDetector(threshold=0.02),
        hardware=hw,
        ble=ble,
        store=PhotoStore(tmp_path / "photos"),
        clock=clock,
        sleep=lambda _s: None,
    )
    for _ in range(3):
        orch.tick()
    assert not any(c.startswith("home") for c in hw.calls)
