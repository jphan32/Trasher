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
        ctrls: dict = {}
        # 전체 센서 FOV(줌인 방지): ScalerCrop=전체 픽셀어레이. IMX219 저해상도 중앙크롭 회피.
        try:
            w, h = self._cam.camera_properties["PixelArraySize"]
            ctrls["ScalerCrop"] = (0, 0, int(w), int(h))
        except Exception:  # noqa: BLE001 - 속성 미지원이면 기본 동작 유지
            pass
        # 화이트밸런스: 부스 조명 고정 → 수동 ColourGains(AWB off) 일관. AWB는 색 물체에 흔들려
        # 흰 종이가 분홍/적색 캐스트됨(실측). gain≤0이면 auto. 현장 조명에 맞게 재보정.
        v = self._cfg
        if v.awb_red_gain > 0 and v.awb_blue_gain > 0:
            ctrls["AwbEnable"] = False
            ctrls["ColourGains"] = (v.awb_red_gain, v.awb_blue_gain)
        if ctrls:
            self._cam.set_controls(ctrls)

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
