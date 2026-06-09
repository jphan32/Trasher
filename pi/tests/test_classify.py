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
    text = json.dumps(
        {
            "category": category,
            "description": "헹궈 배출.",
            "confidence": conf,
            "eco_points": 55,
            "recyclable": True,
        }
    )
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
    c = Classification.from_response(
        {"category": "PET", "confidence": 1.5, "eco_points": 150, "recyclable": True}
    )
    assert c.category == "pet"
    assert c.confidence == 1.0
    assert c.eco_points == 100  # 0~100으로 클램프
    assert c.recyclable is True
    assert Classification.from_response({"category": "glass"}).category == "other"


def test_eco_points_zeroed_when_not_recyclable() -> None:
    # 재활용 불가면 모델이 점수를 줘도 0으로 강제(보상 일관성). docs §4.6
    c = Classification.from_response(
        {"category": "other", "eco_points": 40, "recyclable": False}
    )
    assert c.recyclable is False
    assert c.eco_points == 0
    # 누락 시 안전 기본값
    d = Classification.from_response({"category": "other"})
    assert d.eco_points == 0 and d.recyclable is False
    # 엄격 정규화: 문자열 "false"가 truthy로 새지 않는다(실제 bool True만 인정)
    e = Classification.from_response(
        {"category": "pet", "eco_points": 50, "recyclable": "false"}
    )
    assert e.recyclable is False and e.eco_points == 0


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
    results = [mc.classify(b"x") for _ in range(4)]
    assert [r.category for r in results] == ["pet", "can", "other", "other"]
    assert all(r.description for r in results)  # 팁 비어있지 않음
    # eco_points/recyclable 회전: pet/can/유리는 재활용 양수, 마지막 일반쓰레기는 0
    assert [r.eco_points for r in results] == [60, 55, 30, 0]
    assert [r.recyclable for r in results] == [True, True, True, False]


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
