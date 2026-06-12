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

    @abstractmethod
    def home(self, *, reseat: bool) -> None:
        """서보 3개를 홈(게이트 닫힘 + 분기 중앙)으로 복귀. 물리 리셋 버튼이 호출.

        연속회전 서보는 위치 피드백이 없어 '홈'은 기계식 하드스톱으로만 정의된다.
        - ``reseat=False``(짧게-클릭): 구동 없이 무신호(detach) — 현재 위치를 홈으로 간주.
        - ``reseat=True``(길게-클릭): 닫힘/중앙 방향으로 ``servo.rehome_s`` 동안 구동해 하드스톱에
          다시 안착(재시팅)시킨 뒤 detach. 드리프트/잼 복구용.
        """

    def close(self) -> None:  # noqa: B027 - 선택적 override(기본 no-op)
        """리소스 정리(GPIO 해제 등). 실기기 구현만 override."""
