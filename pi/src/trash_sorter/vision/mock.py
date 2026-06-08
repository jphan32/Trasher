"""Mock 카메라. 스크립트된 프레임 시퀀스를 재생하고, 사진 캡처는 더미 JPEG를 쓴다."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

import numpy as np

from .base import Camera, Frame


class MockCamera(Camera):
    def __init__(
        self,
        frames: Iterable[Frame] | None = None,
        photo_size: tuple[int, int] = (1280, 720),
    ) -> None:
        self._frames: Iterator[Frame] = iter(frames) if frames is not None else iter(())
        self._photo_size = photo_size
        self.captured: list[str] = []
        self._last = np.zeros((48, 64), dtype=np.uint8)

    def read_frame(self) -> Frame:
        try:
            self._last = np.asarray(next(self._frames))
        except StopIteration:
            pass  # 시퀀스 끝나면 마지막 프레임 유지(정지 상태)
        return self._last

    def capture_photo(self, path: str) -> tuple[int, int]:
        # 실제 디코딩 없는 더미 파일. HTTP 서버 테스트가 바이트를 읽을 수 있게.
        with open(path, "wb") as f:
            f.write(b"\xff\xd8\xff\xe0MOCKJPEG\xff\xd9")
        self.captured.append(path)
        return self._photo_size


def blank(value: int = 0, shape: tuple[int, int] = (48, 64)) -> np.ndarray:
    return np.full(shape, value, dtype=np.uint8)
