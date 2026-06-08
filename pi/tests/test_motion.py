"""변이검출 테스트 (합성 프레임)."""

from __future__ import annotations

from trash_sorter.vision import MotionDetector
from trash_sorter.vision.mock import MockCamera, blank


def test_first_frame_no_motion() -> None:
    md = MotionDetector(threshold=0.02)
    assert md.changed_ratio(blank(0)) == 0.0
    assert md.is_motion(blank(0)) is False


def test_static_scene_no_motion() -> None:
    md = MotionDetector(threshold=0.02)
    md.changed_ratio(blank(100))
    assert md.is_motion(blank(100)) is False  # 동일 프레임


def test_object_inserted_triggers_motion() -> None:
    md = MotionDetector(threshold=0.02)
    md.changed_ratio(blank(0))           # 빈 장면
    assert md.is_motion(blank(200)) is True  # 밝은 물체 투입 → 전 픽셀 변화


def test_mock_camera_plays_scripted_frames() -> None:
    cam = MockCamera(frames=[blank(0), blank(255)])
    md = MotionDetector(threshold=0.02)
    md.changed_ratio(cam.read_frame())     # 0
    assert md.is_motion(cam.read_frame())  # 255 → 변이


def test_mock_camera_capture_writes_file(tmp_path) -> None:
    cam = MockCamera(photo_size=(640, 480))
    path = str(tmp_path / "1.jpg")
    w, h = cam.capture_photo(path)
    assert (w, h) == (640, 480)
    assert cam.captured == [path]
    assert (tmp_path / "1.jpg").read_bytes().startswith(b"\xff\xd8")
