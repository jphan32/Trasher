"""Mock 하드웨어. macOS/CI 개발·테스트용. 호출 이력을 기록한다."""

from __future__ import annotations

from dataclasses import dataclass, field

from .base import HardwareController, Route


@dataclass
class MockHardware(HardwareController):
    gate_open: bool = False
    route: Route = "center"
    belt_on: bool = False
    calls: list[str] = field(default_factory=list)

    def set_gate(self, *, open: bool) -> None:
        self.gate_open = open
        self.calls.append(f"gate:{'open' if open else 'closed'}")

    def set_route(self, route: Route) -> None:
        self.route = route
        self.calls.append(f"route:{route}")

    def belt(self, *, on: bool) -> None:
        self.belt_on = on
        self.calls.append(f"belt:{'on' if on else 'off'}")

    def stop_all(self) -> None:
        # gpiozero 구현과 동일: 벨트 정지 + 게이트 홀드(닫힘).
        self.belt_on = False
        self.gate_open = False
        self.calls.append("stop_all")

    def home(self, *, reseat: bool) -> None:
        # 짧게=detach(구동 없음) / 길게=재시팅 구동 — 어느 쪽이든 논리 상태는 홈(게이트 닫힘+중앙).
        self.gate_open = False
        self.route = "center"
        self.calls.append(f"home:{'reseat' if reseat else 'detach'}")
