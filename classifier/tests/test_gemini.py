"""GeminiClassifier 테스트 — FakeSession으로 네트워크 없이."""

from __future__ import annotations

import pytest

from conftest import FakeResp, FakeSession, dummy_prompts, dummy_settings, gemini_ok
from trash_classifier.gemini import ClassificationError, GeminiClassifier


def _classifier(resp: FakeResp) -> tuple[GeminiClassifier, FakeSession]:
    session = FakeSession(resp)
    return GeminiClassifier(dummy_settings(), dummy_prompts(), session=session), session


def test_classify_parses_structured_output() -> None:
    clf, session = _classifier(FakeResp(200, gemini_ok(category="can", conf=0.92)))
    result = clf.classify(b"\xff\xd8jpeg", mime="image/jpeg")
    assert result.category == "can"
    assert result.confidence == 0.92
    assert "캔" in result.description
    # 요청 본문에 structured output 스키마와 이미지가 들어갔는지
    _url, body, _t = session.calls[0]
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["responseSchema"]["properties"]["category"]["enum"] == [
        "pet", "can", "other"
    ]
    assert body["contents"][0]["parts"][0]["inline_data"]["mime_type"] == "image/jpeg"


def test_non_200_raises() -> None:
    clf, _ = _classifier(FakeResp(403, {"error": "denied"}))
    with pytest.raises(ClassificationError):
        clf.classify(b"x")


def test_missing_candidates_raises() -> None:
    clf, _ = _classifier(FakeResp(200, {"candidates": []}))
    with pytest.raises(ClassificationError):
        clf.classify(b"x")


def test_malformed_json_text_raises() -> None:
    bad = {"candidates": [{"content": {"parts": [{"text": "not json"}]}}]}
    clf, _ = _classifier(FakeResp(200, bad))
    with pytest.raises(ClassificationError):
        clf.classify(b"x")
