"""비전 튜닝 도구 테스트 — analyze/summarize/load_frames."""

from __future__ import annotations

import numpy as np

from trash_sorter.vision.mock import blank
from trash_sorter.vision.tuning import analyze, load_frames, summarize


def test_analyze_flags_motion_on_change() -> None:
    frames = [blank(0), blank(0), blank(255), blank(255)]
    stats = analyze(frames, threshold=0.02)
    assert stats[0].ratio == 0.0  # 첫 프레임
    assert stats[1].motion is False  # 정지
    assert stats[2].motion is True  # blank0 → blank255 (전 픽셀 변화)
    assert stats[3].motion is False  # 다시 정지


def test_summarize_reports_distribution() -> None:
    frames = [blank(0), blank(0), blank(255), blank(255), blank(0)]
    stats = analyze(frames, threshold=0.02)
    s = summarize(stats, threshold=0.02)
    assert s.count == 5
    assert s.max_ratio == 1.0  # 완전 전환 프레임 존재
    assert s.motion_frames >= 2
    assert 0.0 <= s.suggested_threshold <= 1.0


def test_load_frames_from_npy(tmp_path) -> None:
    np.save(tmp_path / "001.npy", blank(0))
    np.save(tmp_path / "002.npy", blank(255))
    frames = load_frames(tmp_path)
    assert len(frames) == 2
    assert frames[0].mean() == 0
    assert frames[1].mean() == 255


def test_load_frames_empty_dir_raises(tmp_path) -> None:
    import pytest

    with pytest.raises(FileNotFoundError):
        load_frames(tmp_path)
