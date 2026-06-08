"""Pi 분류 모듈 테스트 — schema/gemini(mock)/prompts/Mock."""

from __future__ import annotations

import json
from typing import Any

import pytest

from trash_sorter.classify import (
    Classification,
    ClassificationError,
    GeminiClassifier,
    MockClassifier,
    build_classifier,
)
from trash_sorter.classify.config import ClassifierConfig
from trash_sorter.classify.prompts import Prompts, load_prompts
from trash_sorter.classify.schema import WASTE_CATEGORIES


class FakeResp:
    def __init__(self, status: int, payload: Any) -> None:
        self.status_code = status
        self._p = payload
        self.text = json.dumps(payload) if isinstance(payload, dict | list) else str(payload)

    def json(self) -> Any:
        return self._p


class FakeSession:
    def __init__(self, resp: FakeResp) -> None:
        self.resp = resp
        self.calls: list[tuple] = []

    def post(self, url: str, json: Any = None, timeout: float = 0) -> FakeResp:
        self.calls.append((url, json, timeout))
        return self.resp


def _gemini_ok(category: str = "can", conf: float = 0.9) -> dict:
    text = json.dumps({"category": category, "description": "헹궈 배출.", "confidence": conf})
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def _cfg() -> ClassifierConfig:
    return ClassifierConfig(
        credentials_path="", model="gemini-3.5-flash", timeout_s=5.0, temperature=0.0
    )


def _prompts() -> Prompts:
    return Prompts(system_instruction="sys", classify_prompt="분류")


def test_schema_categories() -> None:
    assert set(WASTE_CATEGORIES) == {"pet", "can", "other"}


def test_classification_from_response_normalizes() -> None:
    c = Classification.from_response({"category": "PET", "confidence": 1.5})
    assert c.category == "pet"
    assert c.confidence == 1.0
    assert Classification.from_response({"category": "glass"}).category == "other"


def test_gemini_classify_parses_structured_output() -> None:
    session = FakeSession(FakeResp(200, _gemini_ok("pet", 0.97)))
    result = GeminiClassifier(_cfg(), _prompts(), session=session).classify(b"\xff\xd8")
    assert result.category == "pet"
    assert result.confidence == 0.97
    _url, body, _t = session.calls[0]
    assert body["generationConfig"]["responseMimeType"] == "application/json"


def test_gemini_non_200_raises() -> None:
    session = FakeSession(FakeResp(403, {"error": "denied"}))
    with pytest.raises(ClassificationError):
        GeminiClassifier(_cfg(), _prompts(), session=session).classify(b"x")


def test_mock_classifier_rotates_with_tips() -> None:
    mc = MockClassifier()
    cats = [mc.classify(b"x").category for _ in range(3)]
    assert cats == ["pet", "can", "other"]
    assert mc.classify(b"x").description  # 팁 비어있지 않음


def test_build_classifier_falls_back_to_mock_without_key() -> None:
    cfg = ClassifierConfig(credentials_path="", model="m", timeout_s=5, temperature=0)
    assert isinstance(build_classifier(cfg), MockClassifier)


def test_load_prompts_has_categories() -> None:
    p = load_prompts()
    for cat in ("pet", "can", "other"):
        assert cat in p.system_instruction


class SeqSession:
    """호출마다 다음 응답(또는 예외)을 반환 — 재시도 테스트용."""

    def __init__(self, items: list) -> None:
        self._items = items
        self.calls = 0

    def post(self, url: str, json: Any = None, timeout: float = 0) -> Any:
        item = self._items[self.calls]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item


def _gemini_seq(items: list) -> GeminiClassifier:
    return GeminiClassifier(_cfg(), _prompts(), session=SeqSession(items), sleep=lambda _s: None)


def test_retry_succeeds_after_transient() -> None:
    clf = _gemini_seq([FakeResp(429, {"e": 1}), FakeResp(200, _gemini_ok("pet"))])
    assert clf.classify(b"x").category == "pet"  # 429 후 200 → 성공


def test_retry_exhausted_raises() -> None:
    # max_retries=2 → 3회 시도 모두 503이면 실패
    clf = _gemini_seq([FakeResp(503, {}), FakeResp(503, {}), FakeResp(503, {})])
    with pytest.raises(ClassificationError):
        clf.classify(b"x")


def test_network_error_is_retried() -> None:
    clf = _gemini_seq([ConnectionError("boom"), FakeResp(200, _gemini_ok("can"))])
    assert clf.classify(b"x").category == "can"  # 네트워크 오류 후 성공


def test_non_transient_status_not_retried() -> None:
    session = SeqSession([FakeResp(403, {"e": "denied"}), FakeResp(200, _gemini_ok())])
    clf = GeminiClassifier(_cfg(), _prompts(), session=session, sleep=lambda _s: None)
    with pytest.raises(ClassificationError):
        clf.classify(b"x")
    assert session.calls == 1  # 403은 즉시 실패(재시도 안 함)
