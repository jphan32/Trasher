"""프레임 차분 변이검출. 순수 numpy(opencv 불필요) → macOS에서 테스트 가능.

연속 프레임의 픽셀 변화 비율을 계산한다. 안정화(settle) 타이밍은 오케스트레이터가 관리하고,
여기서는 프레임별 변화량/변이여부만 보고한다.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np

from .base import Frame


class MotionDetector:
    def __init__(
        self,
        threshold: float = 0.02,
        pixel_delta: int = 25,
        *,
        threshold_provider: Callable[[], float] | None = None,
    ) -> None:
        """threshold: 변화로 칠 픽셀 비율. pixel_delta: 픽셀당 변화 인정 최소 차(0-255).

        threshold_provider: 주어지면 ``is_motion`` 이 매번 이 콜백으로 임계값을 **live** 조회한다
        (런타임 튜닝 ``PUT /config`` 의 ``vision.motion_threshold`` in-place 변경을 즉시 반영, HOT).
        미지정이면 생성 시 ``threshold`` 고정값 사용(tuning.py CLI 등). docs/protocol.md §8.
        """
        self._threshold = threshold
        self._pixel_delta = pixel_delta
        self._threshold_provider = threshold_provider
        self._prev: np.ndarray | None = None

    def reset(self) -> None:
        self._prev = None

    def changed_ratio(self, frame: Frame) -> float:
        """직전 프레임 대비 변화 픽셀 비율(0.0-1.0). 첫 프레임은 0.0."""
        cur = np.asarray(frame)
        prev = self._prev
        self._prev = cur
        if prev is None or prev.shape != cur.shape:
            return 0.0
        diff = np.abs(cur.astype(np.int16) - prev.astype(np.int16))
        changed = np.count_nonzero(diff > self._pixel_delta)
        return float(changed) / float(cur.size)

    def is_motion(self, frame: Frame) -> bool:
        threshold = self._threshold_provider() if self._threshold_provider else self._threshold
        return self.changed_ratio(frame) > threshold
