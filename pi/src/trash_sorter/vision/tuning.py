"""변이검출 임계값 보정 도구 — 프레임 시퀀스의 changed_ratio를 분석.

motion_threshold / pixel_delta(config)를 현장 카메라에 맞게 보정하는 데 쓴다.
프레임은 ``.npy``(numpy 저장) 우선, 없으면 이미지 파일(cv2 가드, Pi 전용)로 로드한다.

실행: `trash-sorter --tune <frames_dir> [--threshold 0.02] [--pixel-delta 25]`
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .base import Frame
from .motion import MotionDetector


@dataclass(frozen=True)
class FrameStat:
    index: int
    ratio: float
    motion: bool


def analyze(
    frames: list[Frame], *, threshold: float = 0.02, pixel_delta: int = 25
) -> list[FrameStat]:
    """각 프레임의 직전 대비 변화 비율과 모션 여부를 계산."""
    md = MotionDetector(threshold=threshold, pixel_delta=pixel_delta)
    stats: list[FrameStat] = []
    for i, frame in enumerate(frames):
        ratio = md.changed_ratio(frame)
        stats.append(FrameStat(index=i, ratio=ratio, motion=ratio > threshold))
    return stats


@dataclass(frozen=True)
class Summary:
    count: int
    max_ratio: float
    mean_ratio: float
    motion_frames: int
    suggested_threshold: float


def summarize(stats: list[FrameStat], threshold: float) -> Summary:
    """보정 보조: 변화 비율 분포 + 제안 임계값(상위/하위 사이 중앙값 근처)."""
    ratios = [s.ratio for s in stats[1:]]  # 첫 프레임(0.0) 제외
    if not ratios:
        return Summary(len(stats), 0.0, 0.0, 0, threshold)
    arr = np.asarray(ratios)
    # 제안: 95퍼센타일과 50퍼센타일의 기하 평균 근처(정지 잡음 위, 모션 아래)
    p50, p95 = float(np.percentile(arr, 50)), float(np.percentile(arr, 95))
    suggested = round((p50 * p95) ** 0.5, 4) if p50 > 0 and p95 > 0 else threshold
    return Summary(
        count=len(stats),
        max_ratio=round(float(arr.max()), 4),
        mean_ratio=round(float(arr.mean()), 4),
        motion_frames=sum(1 for s in stats if s.motion),
        suggested_threshold=suggested,
    )


def load_frames(directory: str | Path) -> list[Frame]:
    """디렉터리에서 프레임 로드. .npy 우선, 없으면 이미지(cv2, Pi 전용)."""
    d = Path(directory)
    npys = sorted(d.glob("*.npy"))
    if npys:
        return [np.load(p) for p in npys]

    images = sorted(p for p in d.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if not images:
        raise FileNotFoundError(f"{d}에 .npy 또는 이미지 프레임이 없습니다")
    try:
        import cv2  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover - Pi 전용
        raise RuntimeError("이미지 로드에는 opencv가 필요합니다(Pi: pip install -r requirements-pi.txt)") from e
    return [cv2.imread(str(p), cv2.IMREAD_GRAYSCALE) for p in images]  # pragma: no cover


def run_cli(directory: str, *, threshold: float = 0.02, pixel_delta: int = 25) -> None:  # pragma: no cover
    frames = load_frames(directory)
    stats = analyze(frames, threshold=threshold, pixel_delta=pixel_delta)
    print(f"# {len(frames)} frames, threshold={threshold}, pixel_delta={pixel_delta}")
    print(f"{'idx':>5} {'ratio':>10} {'motion':>7}")
    for s in stats:
        print(f"{s.index:>5} {s.ratio:>10.4f} {'YES' if s.motion else '':>7}")
    summary = summarize(stats, threshold)
    print(
        f"# max={summary.max_ratio} mean={summary.mean_ratio} "
        f"motion_frames={summary.motion_frames}/{summary.count} "
        f"suggested_threshold={summary.suggested_threshold}"
    )
