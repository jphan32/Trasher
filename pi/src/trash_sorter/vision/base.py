"""카메라 인터페이스. docs/protocol.md §2(capturing), config VisionConfig.

- ``read_frame()``: 변이검출용 저해상 그레이스케일 프레임(numpy 2D, uint8)
- ``capture_photo(path)``: 전해상 JPEG 저장 → (width, height) 반환
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

Frame = Any  # numpy.ndarray (2D uint8). numpy 미설치 환경 대비 Any.


class Camera(ABC):
    @abstractmethod
    def read_frame(self) -> Frame:
        """변이검출용 그레이스케일 프레임 1장."""

    @abstractmethod
    def capture_photo(self, path: str) -> tuple[int, int]:
        """전해상 사진을 path에 JPEG로 저장. (w, h) 반환."""

    def close(self) -> None:  # noqa: B027 - 선택적 override(기본 no-op)
        """리소스 정리. 실기기 구현만 override."""
