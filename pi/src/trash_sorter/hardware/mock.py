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
        self.belt_on = False
        self.calls.append("stop_all")
