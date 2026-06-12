"""물리 리셋 버튼 — GPIO 입력 + 디바운스 + 짧게/길게 판정.

구성(벨트와 같은 분리 패턴):
- ``ButtonInput``(ABC): 현재 눌림 여부(raw)만 노출. ``MockButton``(호스트) / ``GpiozeroButton``(Pi).
- ``PressDetector``: **순수 로직**(하드웨어·스레드 비의존, clock 주입). 매 tick raw 상태를 받아
  ① 채터링 디바운스 ② 짧게/길게 분류를 한다. 그래서 macOS에서 결정적으로 테스트된다.

오케스트레이터(app.py)가 매 tick ``PressDetector.update(button.is_pressed(), clock())``를 호출하고,
반환된 이벤트로 서보 홈 복귀를 수행한다(짧게=detach-홈 / 길게=타이머 재시팅).

라이브 GPIO는 Raspberry Pi에서만 가능(gpiozero는 지연 import) — 이 모듈은 macOS에서도 import된다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from ..config import Settings


class ButtonEvent(StrEnum):
    SHORT = "short"  # 짧게 클릭 → detach-홈(구동 없이 현재 위치를 홈으로)
    LONG = "long"    # 길게 클릭 → 타이머 재시팅(닫힘/중앙 하드스톱으로 구동 후 홈)


class ButtonInput(ABC):
    """버튼 raw 입력. 디바운스/판정은 PressDetector가 하므로 여기선 순간 눌림만 반환."""

    @abstractmethod
    def is_pressed(self) -> bool:
        """현재 버튼이 눌려 있으면 True(raw, 디바운스 전)."""

    def close(self) -> None:  # noqa: B027 - 선택적 override(기본 no-op)
        """리소스 정리(GPIO 해제 등)."""


@dataclass
class MockButton(ButtonInput):
    """호스트(macOS/CI) 테스트용. ``pressed`` 플래그를 직접 토글해 입력을 흉내낸다."""

    pressed: bool = False

    def is_pressed(self) -> bool:
        return self.pressed


class GpiozeroButton(ButtonInput):
    """실기기 버튼(gpiozero ``Button``). 배선: GPIO ↔ 버튼 ↔ GND(pull_up=True, 눌림=LOW).

    디바운스는 소프트웨어(PressDetector)가 담당하므로 gpiozero ``bounce_time``은 두지 않는다
    (이중 디바운스로 지연이 늘지 않게). 순간 핀 상태만 폴링한다.
    """

    def __init__(self, settings: Settings) -> None:
        try:
            from gpiozero import Button  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover - Pi 전용
            raise RuntimeError(
                "gpiozero를 불러올 수 없습니다(리셋 버튼). "
                "Raspberry Pi에서 requirements-pi.txt 설치 후 실행하세요."
            ) from e
        b = settings.button
        self._btn = Button(b.pin, pull_up=b.pull_up)

    def is_pressed(self) -> bool:
        return bool(self._btn.is_pressed)

    def close(self) -> None:  # pragma: no cover - Pi 전용
        self._btn.close()


class PressDetector:
    """폴링 기반 디바운스 + 짧게/길게 분류(순수 로직, clock 주입).

    매 tick ``update(raw_pressed, now)``:
    - **디바운스(채터링 방지)**: raw가 ``debounce_s`` 이상 안정돼야 논리 상태(_stable) 전이를 확정.
      바운스로 raw가 흔들리면 타이머가 리셋돼 전이가 일어나지 않는다.
    - **짧게/길게**: 논리적 눌림이 ``long_press_s`` 이상이면 (릴리스 전이라도) **LONG 1회** 즉시
      방출(빠른 피드백). 그 전에 릴리스되면 **SHORT 1회**. 한 누름은 정확히 한 이벤트만 낸다.
    """

    def __init__(self, *, debounce_s: float, long_press_s: float) -> None:
        self._debounce_s = max(0.0, debounce_s)
        self._long_s = max(0.0, long_press_s)
        self._stable = False           # 디바운스된 논리 눌림 상태
        self._last_raw = False         # 직전 raw 표본
        self._last_change = 0.0        # raw가 마지막으로 바뀐 시각(안정 타이머 기준)
        self._press_start: float | None = None
        self._fired_long = False

    def update(self, raw: bool, now: float) -> ButtonEvent | None:
        # 1) 디바운스: raw가 흔들리면 타이머 리셋, debounce_s 안정 시에만 _stable 전이 확정.
        if raw != self._last_raw:
            self._last_raw = raw
            self._last_change = now
        elif raw != self._stable and now - self._last_change >= self._debounce_s:
            self._stable = raw
            event = self._on_edge(now)
            if event is not None:
                return event

        # 2) 눌림 유지 중 long 임계 도달 → LONG 1회(릴리스를 기다리지 않음).
        if (
            self._stable
            and not self._fired_long
            and self._press_start is not None
            and now - self._press_start >= self._long_s
        ):
            self._fired_long = True
            return ButtonEvent.LONG
        return None

    def _on_edge(self, now: float) -> ButtonEvent | None:
        if self._stable:  # 눌림 시작
            # long 임계는 '물리적 눌림 시각'(=raw가 True로 바뀐 _last_change)부터 측정 —
            # 디바운스 확정 시각(now)부터 재면 debounce_s만큼 늦게 잡혀 체감 임계가 길어진다.
            self._press_start = self._last_change
            self._fired_long = False
            return None
        # 릴리스: LONG을 이미 냈으면 무이벤트, 아니면 SHORT.
        fired = self._fired_long
        self._press_start = None
        self._fired_long = False
        return None if fired else ButtonEvent.SHORT
