"""비전 계층: 카메라(저해상 스트림 + 사진 캡처) + 프레임차분 변이검출."""

from .base import Camera, Frame
from .mock import MockCamera
from .motion import MotionDetector

__all__ = ["Camera", "Frame", "MockCamera", "MotionDetector"]
