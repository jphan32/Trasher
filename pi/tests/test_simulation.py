"""시뮬레이션 모드 테스트 — 하드웨어 없이 전 사이클이 도는지 검증."""

from __future__ import annotations

from trash_sorter.config import BeltConfig, Settings, VisionConfig
from trash_sorter.protocol import PiState, WasteCategory
from trash_sorter.sim import Simulation, sim_frames


class FakeClock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def _fast_settings() -> Settings:
    # 타이머를 0으로 줄여 적은 tick으로 사이클 완료(결정적).
    return Settings(
        belt=BeltConfig(run_seconds=0.0),
        vision=VisionConfig(settle_seconds=0.0),
    )


def test_sim_frames_pulse_triggers_motion() -> None:
    gen = sim_frames()
    frames = [next(gen) for _ in range(4)]
    # blank0, blank0, blank255, ... → 세 번째에서 변화(모션)
    assert frames[0].mean() == 0
    assert frames[2].mean() == 255


def test_simulation_runs_cycles_without_hardware() -> None:
    clock = FakeClock()
    sim = Simulation(_fast_settings(), clock=clock, sleep=lambda _s: None)
    # 충분한 tick 동안 클럭을 전진시키며 구동
    for _ in range(200):
        clock.t += 0.05
        sim.tick()

    # 적어도 한 사이클 완료(가짜 iPad가 결과 회신)
    assert sim.cycles_completed >= 1
    # PhotoReady 발행됨
    assert len(sim.ble.photos) >= 1
    # 하드웨어가 실제로 분기·벨트 구동(route + belt 호출)
    assert any(c.startswith("route:") for c in sim.hw.calls)
    assert "belt:on" in sim.hw.calls
    # 결과대로 sort되어 lastSort가 노출됨
    sorted_statuses = [s for s in sim.ble.statuses if s.last_sort is not None]
    assert sorted_statuses
    assert sorted_statuses[-1].last_sort in set(WasteCategory)


def test_simulation_returns_to_idle_after_cycle() -> None:
    clock = FakeClock()
    sim = Simulation(_fast_settings(), clock=clock, sleep=lambda _s: None)
    for _ in range(200):
        clock.t += 0.05
        sim.tick()
    # 사이클을 돌고 다시 감지 대기로 복귀할 수 있어야 함(멈추지 않음)
    assert sim.orchestrator._sm.state in {  # noqa: SLF001
        PiState.IDLE,
        PiState.DETECTING,
        PiState.CAPTURING,
        PiState.AWAITING_RESULT,
        PiState.SORTING,
    }
    assert sim.cycles_completed >= 2  # 여러 사이클 반복
