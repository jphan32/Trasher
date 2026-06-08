"""실 Gemini 라이브 스모크 — 기본 skip. `CLASSIFIER_LIVE=1`에서만 실행.

실제 GCP 자격증명 + 네트워크가 필요하므로 CI/일반 테스트에서는 제외된다.
실행: CLASSIFIER_LIVE=1 CLASSIFIER_CREDENTIALS=<key> uv run --with pillow pytest tests/test_live.py
"""

from __future__ import annotations

import importlib.util
import io
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("CLASSIFIER_LIVE") != "1",
    reason="CLASSIFIER_LIVE=1에서만 실행(실 Gemini 호출)",
)


def _jpeg() -> bytes:
    if importlib.util.find_spec("PIL") is None:
        pytest.skip("pillow 필요(uv run --with pillow)")
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, format="JPEG")
    return buf.getvalue()


def test_live_classify_returns_valid_schema() -> None:
    from trash_classifier.config import load_settings
    from trash_classifier.gemini import GeminiClassifier
    from trash_classifier.prompts import load_prompts

    settings = load_settings()
    if not Path(settings.credentials_path).is_file():
        pytest.skip(f"자격증명 없음: {settings.credentials_path}")

    result = GeminiClassifier(settings, load_prompts()).classify(_jpeg())
    assert result.category in {"pet", "can", "other"}
    assert result.description  # 재활용 팁 비어있지 않음
    assert 0.0 <= result.confidence <= 1.0
