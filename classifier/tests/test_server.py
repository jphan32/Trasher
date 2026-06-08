"""Flask 프록시 엔드포인트 테스트 — 실 classifier + FakeSession."""

from __future__ import annotations

import io

from conftest import FakeResp, FakeSession, dummy_prompts, dummy_settings, gemini_ok
from trash_classifier.gemini import GeminiClassifier
from trash_classifier.server import create_app


def _client(resp: FakeResp):
    clf = GeminiClassifier(dummy_settings(), dummy_prompts(), session=FakeSession(resp))
    return create_app(clf, dummy_settings()).test_client()


def test_health() -> None:
    c = _client(FakeResp(200, gemini_ok()))
    r = c.get("/health")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    assert r.get_json()["model"] == "gemini-3.5-flash"


def test_classify_multipart_returns_result() -> None:
    ok = gemini_ok(category="pet", desc="페트병은 라벨 떼고 압착.", conf=0.97)
    c = _client(FakeResp(200, ok))
    r = c.post("/classify", data={"image": (io.BytesIO(b"\xff\xd8jpeg"), "trash.jpg")},
               content_type="multipart/form-data")
    assert r.status_code == 200
    body = r.get_json()
    assert body["category"] == "pet"
    assert body["confidence"] == 0.97
    assert "페트" in body["description"]


def test_classify_raw_body() -> None:
    c = _client(FakeResp(200, gemini_ok()))
    r = c.post("/classify", data=b"\xff\xd8jpeg", content_type="image/jpeg")
    assert r.status_code == 200
    assert r.get_json()["category"] == "can"


def test_classify_empty_returns_400() -> None:
    c = _client(FakeResp(200, gemini_ok()))
    r = c.post("/classify", data=b"", content_type="image/jpeg")
    assert r.status_code == 400


def test_classify_upstream_error_returns_502() -> None:
    c = _client(FakeResp(500, {"error": "boom"}))
    r = c.post("/classify", data=b"\xff\xd8jpeg", content_type="image/jpeg")
    assert r.status_code == 502
    assert "error" in r.get_json()
