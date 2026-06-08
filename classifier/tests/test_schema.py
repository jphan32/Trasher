"""분류 스키마/검증 테스트."""

from __future__ import annotations

from trash_classifier.schema import RESPONSE_SCHEMA, WASTE_CATEGORIES, Classification


def test_categories_match_protocol() -> None:
    assert set(WASTE_CATEGORIES) == {"pet", "can", "other"}
    assert RESPONSE_SCHEMA["properties"]["category"]["enum"] == ["pet", "can", "other"]


def test_from_response_valid() -> None:
    c = Classification.from_response({"category": "PET", "description": " 팁 ", "confidence": 0.93})
    assert c.category == "pet"           # 소문자 정규화
    assert c.description == "팁"          # 트림
    assert c.confidence == 0.93


def test_unknown_category_falls_back_to_other() -> None:
    glass = Classification.from_response({"category": "glass", "confidence": 0.8})
    assert glass.category == "other"
    assert Classification.from_response({}).category == "other"


def test_confidence_clamped_and_safe() -> None:
    assert Classification.from_response({"category": "can", "confidence": 1.7}).confidence == 1.0
    assert Classification.from_response({"category": "can", "confidence": -0.5}).confidence == 0.0
    assert Classification.from_response({"category": "can", "confidence": "nan?"}).confidence == 0.0


def test_to_dict_roundtrip_keys() -> None:
    c = Classification.from_response({"category": "can", "description": "x", "confidence": 0.5})
    assert set(c.to_dict()) == {"category", "description", "confidence"}
