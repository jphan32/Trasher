"""/classify 응답 교차언어 계약 — 골든 픽스처(fixtures/classify-response.json) Pi 측 검증.

iOS PiClassificationContractTests가 같은 파일을 파싱 검증한다. 드리프트 시 한쪽이 깨진다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from trash_sorter.classify.schema import WASTE_CATEGORIES, Classification

_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "classify-response.json"


def _cases() -> list[dict]:
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    assert data["proto"] == 1
    return data["cases"]


def test_fixture_exists() -> None:
    assert _FIXTURE.is_file(), f"골든 픽스처 없음: {_FIXTURE}"


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["category"])
def test_response_contract_roundtrips(case: dict) -> None:
    c = Classification.from_response(case)
    assert c.category in WASTE_CATEGORIES
    assert 0.0 <= c.confidence <= 1.0
    assert c.description  # 재활용 팁 존재
    # 정규화된 골든이므로 from_response→to_dict가 원본과 일치(키/값 보존)
    assert c.to_dict() == case
