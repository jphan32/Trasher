"""오케스트레이터 통합 테스트 (전부 mock + 페이크 클락). docs/protocol.md §2,§2.1,§6."""

from __future__ import annotations

import pytest

from trash_sorter.app import Orchestrator
from trash_sorter.ble import MockBleServer
from trash_sorter.config import BeltConfig, Settings
from trash_sorter.hardware import MockHardware
from trash_sorter.protocol import (
    ClassificationResult,
    Command,
    CommandType,
    ErrorCode,
    PiState,
    WasteCategory,
)
from trash_sorter.state import StateMachine
from trash_sorter.vision import MockCamera, MotionDetector
from trash_sorter.vision.mock import blank
from trash_sorter.web.photo_server import PhotoStore


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


def build(tmp_path, frames, *, hardware=None, camera=None, run_seconds=0.0):
    clock = FakeClock()
    ble = MockBleServer()
    hw = hardware if hardware is not None else MockHardware()
    # run_seconds=0 → 논블로킹 sorting이 begin 다음 tick에 즉시 finish (결정적 2-tick).
    # >0 → 벨트가 켜진 'mid-sort' 상태를 검사할 수 있다.
    settings = Settings(belt=BeltConfig(run_seconds=run_seconds))
    orch = Orchestrator(
        settings=settings,
        state=StateMachine(),
        camera=camera if camera is not None else MockCamera(frames=frames),
        motion=MotionDetector(threshold=0.02),
        hardware=hw,
        ble=ble,
        store=PhotoStore(tmp_path / "photos"),
        clock=clock,
        sleep=lambda _s: None,
    )
    return orch, ble, hw, clock


def _motion_frames(n_static: int = 6):
    # blank0 → (motion) blank255, 이후 정지 프레임 다수
    return [blank(0), blank(255), *[blank(255)] * n_static]


def test_gating_no_detection_until_started(tmp_path) -> None:
    orch, ble, _hw, clock = build(tmp_path, _motion_frames())
    for _ in range(4):  # START 안 보냄
        orch.tick()
        clock.advance(0.1)
    assert orch._sm.state is PiState.IDLE  # noqa: SLF001
    assert ble.photos == []


def test_capture_waits_for_motion_stop(tmp_path) -> None:
    # 감지(begin_detection)는 즉시지만, 물체가 움직이는 동안엔 촬영하지 않고
    # 멎은 뒤 settle_seconds 무동작일 때만 촬영(흔들림 방지).
    frames = [blank(0), blank(255), blank(0), blank(255), *[blank(255)] * 4]
    orch, ble, _hw, clock = build(tmp_path, frames)
    ble.simulate_command(Command(cmd=CommandType.START, id=1))
    for _ in range(4):  # START+f1, f2→DETECTING, f3·f4 지속 변이(교대)
        clock.advance(0.6)  # settle(0.5) 넘겨도
        orch.tick()
    assert orch._sm.state is PiState.DETECTING  # noqa: SLF001 - 움직이는 중 → 미촬영
    assert ble.photos == []
    clock.advance(0.6)
    orch.tick()  # 정지 프레임(변이 없음) + settle 경과 → 촬영
    assert orch._sm.state is PiState.AWAITING_RESULT  # noqa: SLF001
    assert len(ble.photos) == 1


def test_capture_forced_after_detect_max(tmp_path) -> None:
    # 움직임이 계속돼 정지하지 않아도 detect_max_seconds 도달 시 강제 촬영(무한 대기 방지).
    frames = [blank(0), *[blank(255), blank(0)] * 60]  # 매 프레임 변이(지속 움직임)
    orch, ble, _hw, clock = build(tmp_path, frames)
    ble.simulate_command(Command(cmd=CommandType.START, id=1))
    orch.tick()  # START + f1
    orch.tick()  # f2 → DETECTING (detect_since=0)
    assert orch._sm.state is PiState.DETECTING  # noqa: SLF001
    for _ in range(30):  # 0.3s×30=9s > detect_max(5s); 매 tick 변이라 settle은 안 됨
        clock.advance(0.3)
        orch.tick()
        if ble.photos:
            break
    assert len(ble.photos) == 1  # detect_max에서 강제 촬영
    assert orch._sm.state is PiState.AWAITING_RESULT  # noqa: SLF001


def _run_full_cycle(orch, ble, clock, category):
    ble.simulate_command(Command(cmd=CommandType.START, id=1))
    orch.tick()  # START 처리
    orch.tick()  # blank0 읽음(첫 프레임, 변이 없음)
    orch.tick()  # blank255 → 변이 감지 → DETECTING
    assert orch._sm.state is PiState.DETECTING  # noqa: SLF001
    clock.advance(0.6)  # settle_seconds(0.5) 경과
    orch.tick()  # 촬영 → AWAITING_RESULT + PhotoReady
    assert orch._sm.state is PiState.AWAITING_RESULT  # noqa: SLF001
    cycle = orch._sm.cycle  # noqa: SLF001
    ble.simulate_result(ClassificationResult(cycle=cycle, category=category, confidence=0.9))
    orch.tick()  # 결과 수신 → SORTING
    orch.tick()  # sort 수행 → IDLE
    return cycle


def test_full_cycle_pet(tmp_path) -> None:
    orch, ble, hw, clock = build(tmp_path, _motion_frames())
    cycle = _run_full_cycle(orch, ble, clock, WasteCategory.PET)

    assert cycle == 1
    assert orch._sm.state is PiState.IDLE  # noqa: SLF001
    # PhotoReady 발행
    assert len(ble.photos) == 1
    assert ble.photos[0].cycle == 1
    assert ble.photos[0].path == "/photos/1.jpg"
    # 분기 경로 = 좌(pet)
    assert "route:left" in hw.calls
    assert hw.calls[-1] == "route:center"  # 중립 복귀
    # 최종 status: sorting 결과 반영
    assert ble.last_status is not None
    assert ble.last_status.last_sort is WasteCategory.PET


@pytest.mark.parametrize(
    "category,route",
    [(WasteCategory.PET, "left"), (WasteCategory.CAN, "right"), (WasteCategory.OTHER, "center")],
)
def test_full_cycle_routes(tmp_path, category, route) -> None:
    orch, ble, hw, clock = build(tmp_path, _motion_frames())
    _run_full_cycle(orch, ble, clock, category)
    assert f"route:{route}" in hw.calls


def test_result_timeout_falls_back_to_other(tmp_path) -> None:
    orch, ble, hw, clock = build(tmp_path, _motion_frames())
    ble.simulate_command(Command(cmd=CommandType.START, id=1))
    for _ in range(3):
        orch.tick()  # → DETECTING
    clock.advance(0.6)
    orch.tick()  # → AWAITING_RESULT
    assert orch._sm.state is PiState.AWAITING_RESULT  # noqa: SLF001

    clock.advance(15.1)  # result_timeout_s(15) 초과, 결과 안 보냄
    orch.tick()  # 타임아웃 → SORTING(other)
    assert ble.last_status is not None
    assert ble.last_status.err is ErrorCode.RESULT_TIMEOUT
    orch.tick()  # SORTING → begin_sort
    orch.tick()  # SORTING → finish_sort → IDLE (run_seconds=0)
    assert "route:center" in hw.calls  # other = 중앙
    assert orch._sm.state is PiState.IDLE  # noqa: SLF001
    # §6: err은 idle 복귀 후 해제됨
    assert orch._sm.snapshot().err is None  # noqa: SLF001


def test_stale_result_ignored(tmp_path) -> None:
    orch, ble, _hw, clock = build(tmp_path, _motion_frames())
    ble.simulate_command(Command(cmd=CommandType.START, id=1))
    for _ in range(3):
        orch.tick()
    clock.advance(0.6)
    orch.tick()  # AWAITING_RESULT, cycle=1
    ble.simulate_result(ClassificationResult(cycle=99, category=WasteCategory.CAN, confidence=0.9))
    orch.tick()
    assert orch._sm.state is PiState.AWAITING_RESULT  # noqa: SLF001  (폐기됨)


def test_estop_command(tmp_path) -> None:
    orch, ble, hw, _clock = build(tmp_path, _motion_frames())
    ble.simulate_command(Command(cmd=CommandType.ESTOP, id=5))
    orch.tick()
    assert orch._sm.state is PiState.ERROR  # noqa: SLF001
    assert "stop_all" in hw.calls
    assert ble.acks[-1].id == 5 and ble.acks[-1].ok is True


def test_manual_sort_command(tmp_path) -> None:
    # run_seconds=0 → begin tick + finish tick. 카테고리 경로 + 완료 후 중립.
    orch, ble, hw, _clock = build(tmp_path, _motion_frames())
    ble.simulate_command(Command(cmd=CommandType.SORT, id=9, arg="can"))
    orch.tick()  # begin_sort
    assert "route:right" in hw.calls
    assert ble.acks[-1].ok is True
    orch.tick()  # _advance_manual_sort → finish (0 경과)
    assert hw.belt_on is False
    assert hw.calls[-1] == "route:center"


def _drive_to_sorting_belt_on(orch, ble, clock):
    """투입→촬영→결과 → SORTING begin_sort까지(벨트 ON, mid-sort). run_seconds>0 전제."""
    ble.simulate_command(Command(cmd=CommandType.START, id=1))
    for _ in range(3):
        orch.tick()
    clock.advance(0.6)
    orch.tick()  # AWAITING
    ble.simulate_result(
        ClassificationResult(cycle=orch._sm.cycle, category=WasteCategory.PET, confidence=0.9)  # noqa: SLF001
    )
    orch.tick()  # SORTING + begin_sort (belt on)


def test_reset_mid_sort_stops_belt(tmp_path) -> None:
    orch, ble, hw, clock = build(tmp_path, _motion_frames(), run_seconds=10.0)
    _drive_to_sorting_belt_on(orch, ble, clock)
    assert hw.belt_on is True  # mid-sort
    ble.simulate_command(Command(cmd=CommandType.RESET, id=2))
    orch.tick()
    assert hw.belt_on is False  # RESET이 벨트를 멈춰야 함
    assert "stop_all" in hw.calls
    assert orch._sm.state is PiState.IDLE  # noqa: SLF001


def test_maintenance_mid_sort_stops_belt(tmp_path) -> None:
    orch, ble, hw, clock = build(tmp_path, _motion_frames(), run_seconds=10.0)
    _drive_to_sorting_belt_on(orch, ble, clock)
    assert hw.belt_on is True
    ble.simulate_command(Command(cmd=CommandType.MAINTENANCE, id=3, arg="true"))
    orch.tick()
    assert hw.belt_on is False  # 점검 진입 전 벨트 정지
    assert orch._sm.state is PiState.MAINTENANCE  # noqa: SLF001


def test_manual_sort_is_nonblocking_and_estop_aborts(tmp_path) -> None:
    orch, ble, hw, _clock = build(tmp_path, _motion_frames(), run_seconds=10.0)
    ble.simulate_command(Command(cmd=CommandType.SORT, id=1, arg="pet"))
    orch.tick()  # begin_sort, 블로킹 없이 즉시 반환
    assert hw.belt_on is True
    assert orch._sm.state is PiState.IDLE  # noqa: SLF001  진단 sort는 사이클 상태 비변경
    ble.simulate_command(Command(cmd=CommandType.ESTOP, id=2))
    orch.tick()  # estop이 매 tick 처리됨(블로킹 없음) → 즉시 정지
    assert hw.belt_on is False
    assert orch._sm.state is PiState.ERROR  # noqa: SLF001


def test_manual_sort_blocks_detection(tmp_path) -> None:
    orch, ble, hw, clock = build(tmp_path, _motion_frames(), run_seconds=10.0)
    ble.simulate_command(Command(cmd=CommandType.START, id=1))
    ble.simulate_command(Command(cmd=CommandType.SORT, id=2, arg="pet"))
    orch.tick()  # 수동 sort begin
    # 수동 sort 중에는 변이가 있어도 감지 시작 안 함
    for _ in range(3):
        orch.tick()
    assert orch._sm.state is PiState.IDLE  # noqa: SLF001  (DETECTING으로 안 감)


def test_heartbeat_emitted_when_idle(tmp_path) -> None:
    orch, ble, _hw, clock = build(tmp_path, _motion_frames())
    orch.tick()  # t=0, 하트비트 없음
    before = len(ble.statuses)
    clock.advance(2.1)  # heartbeat_period(2.0) 초과
    orch.tick()
    assert len(ble.statuses) == before + 1


def test_disconnect_aborts_cycle_and_pauses(tmp_path) -> None:
    orch, ble, hw, clock = build(tmp_path, _motion_frames())
    ble.simulate_command(Command(cmd=CommandType.START, id=1))
    for _ in range(3):
        orch.tick()  # → DETECTING
    assert orch._sm.state is PiState.DETECTING  # noqa: SLF001
    ble.simulate_disconnect()
    orch.tick()
    assert orch._sm.state is PiState.IDLE  # noqa: SLF001
    assert orch._sm.started is False  # noqa: SLF001  재연결 시 start 대기
    assert "stop_all" in hw.calls


class _FailingCamera(MockCamera):
    def capture_photo(self, path: str) -> tuple[int, int]:
        raise OSError("camera down")


def test_camera_failure_transitions_to_error(tmp_path) -> None:
    cam = _FailingCamera(frames=_motion_frames())
    orch, ble, hw, clock = build(tmp_path, None, camera=cam)
    ble.simulate_command(Command(cmd=CommandType.START, id=1))
    for _ in range(3):
        orch.tick()  # → DETECTING
    clock.advance(0.6)
    orch.tick()  # 캡처 시도 → 실패
    assert orch._sm.state is PiState.ERROR  # noqa: SLF001
    assert ble.last_status is not None
    assert ble.last_status.err is ErrorCode.CAMERA_FAIL
    assert "stop_all" in hw.calls


class _FailingHardware(MockHardware):
    def belt(self, *, on: bool) -> None:
        if on:
            raise OSError("motor stuck")
        super().belt(on=on)


def test_motor_failure_transitions_to_error(tmp_path) -> None:
    orch, ble, hw, clock = build(tmp_path, _motion_frames(), hardware=_FailingHardware())
    ble.simulate_command(Command(cmd=CommandType.START, id=1))
    for _ in range(3):
        orch.tick()
    clock.advance(0.6)
    orch.tick()  # AWAITING_RESULT
    ble.simulate_result(
        ClassificationResult(cycle=orch._sm.cycle, category=WasteCategory.PET, confidence=0.9)  # noqa: SLF001
    )
    orch.tick()  # SORTING → begin_sort(belt on) 실패 → ERROR
    assert orch._sm.state is PiState.ERROR  # noqa: SLF001
    assert ble.last_status is not None
    assert ble.last_status.err is ErrorCode.MOTOR_FAIL


@pytest.mark.parametrize(
    "cmd_type,arg",
    [
        (CommandType.BELT, "sideways"),
        (CommandType.BELT, None),
        (CommandType.MAINTENANCE, "maybe"),
        (CommandType.SORT, "glass"),  # 잘못된 카테고리 — 거부(내부오류 아님, m6)
        (CommandType.SORT, None),
    ],
)
def test_invalid_command_arg_acks_false(tmp_path, cmd_type, arg) -> None:
    orch, ble, _hw, _clock = build(tmp_path, _motion_frames())
    ble.simulate_command(Command(cmd=cmd_type, id=11, arg=arg))
    orch.tick()
    assert ble.acks[-1].id == 11
    assert ble.acks[-1].ok is False
    # 검증 실패(거부)는 내부 오류가 아니므로 err=None (m6: INTERNAL과 구분)
    assert ble.acks[-1].err is None


def test_require_arg_rejects_non_string_without_crash(tmp_path) -> None:
    # 잘못된 JSON boolean arg가 들어와도 AttributeError 없이 거부(ok=False).
    assert Orchestrator._require_arg(True, ("true", "false")) is False  # type: ignore[arg-type]
    assert Orchestrator._require_arg(None, ("true", "false")) is False
    assert Orchestrator._require_arg("true", ("true", "false")) is True
