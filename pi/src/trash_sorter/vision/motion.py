"""프레임 차분 변이검출. 순수 numpy(opencv 불필요) → macOS에서 테스트 가능.

연속 프레임의 픽셀 변화 비율을 계산한다. 안정화(settle) 타이밍은 오케스트레이터가 관리하고,
여기서는 프레임별 변화량/변이여부만 보고한다.
"""

from __future__ import annotations

import numpy as np

from .base import Frame


class MotionDetector:
    def __init__(self, threshold: float = 0.02, pixel_delta: int = 25) -> None:
        """threshold: 변화로 칠 픽셀 비율. pixel_delta: 픽셀당 변화 인정 최소 차(0-255)."""
        self._threshold = threshold
        self._pixel_delta = pixel_delta
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
        return self.changed_ratio(frame) > self._threshold
