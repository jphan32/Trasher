"""실기기 카메라 (picamera2 + OpenCV). Raspberry Pi(Linux)에서만 import 가능."""

from __future__ import annotations

from ..config import Settings
from .base import Camera, Frame


class Picamera2Camera(Camera):
    def __init__(self, settings: Settings) -> None:
        try:
            from picamera2 import Picamera2  # type: ignore[import-not-found]
        except ImportError as e:  # pragma: no cover - Pi 전용
            raise RuntimeError(
                "picamera2를 불러올 수 없습니다. "
                "Raspberry Pi에서 `pip install '.[pi]'` 후 실행하세요."
            ) from e

        self._cfg = settings.vision
        self._cam = Picamera2()
        config = self._cam.create_still_configuration(
            main={"size": (self._cfg.width, self._cfg.height)}
        )
        self._cam.configure(config)
        self._cam.start()
        # 전체 센서 FOV 사용(줌인 방지): ScalerCrop을 전체 픽셀어레이로 고정.
        # IMX219 등은 작은/16:9 해상도에서 센서 중앙을 크롭(줌)하므로 4:3 풀해상도 영역을 강제한다.
        try:
            w, h = self._cam.camera_properties["PixelArraySize"]
            self._cam.set_controls({"ScalerCrop": (0, 0, int(w), int(h))})
        except Exception:  # noqa: BLE001 - 속성/컨트롤 미지원이면 기본 동작 유지
            pass

    def read_frame(self) -> Frame:  # pragma: no cover - Pi 전용
        import cv2  # type: ignore[import-not-found]

        rgb = self._cam.capture_array("main")
        return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)

    def capture_photo(self, path: str) -> tuple[int, int]:  # pragma: no cover - Pi 전용
        self._cam.capture_file(path)
        return (self._cfg.width, self._cfg.height)

    def close(self) -> None:  # pragma: no cover - Pi 전용
        self._cam.stop()
        self._cam.close()
