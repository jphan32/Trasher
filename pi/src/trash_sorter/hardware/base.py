"""하드웨어 제어 인터페이스. docs/protocol.md §2.5.

서보 3개(게이트 1 = 정위치 홀드, 분기 좌/우 2) + 벨트 모터 1.
- 게이트: 닫힘=캡처 홀드, 열림=분기 경로로 방출
- 분기: route "left"=좌 열림, "right"=우 열림, "center"=좌·우 닫힘
"""

from __future__ import annotations

from abc import ABC, abstractmethod

Route = str  # "left" | "right" | "center"


class HardwareController(ABC):
    @abstractmethod
    def set_gate(self, *, open: bool) -> None:
        """게이트 서보. open=False는 캡처 존 홀드, True는 방출."""

    @abstractmethod
    def set_route(self, route: Route) -> None:
        """분기 서보 좌/우 설정. 'left'|'right'|'center'."""

    @abstractmethod
    def belt(self, *, on: bool) -> None:
        """컨베이어 벨트 모터 구동/정지."""

    @abstractmethod
    def stop_all(self) -> None:
        """비상 정지: 모든 모터 즉시 정지(벨트 정지, 게이트 홀드)."""

    def close(self) -> None:  # noqa: B027 - 선택적 override(기본 no-op)
        """리소스 정리(GPIO 해제 등). 실기기 구현만 override."""
