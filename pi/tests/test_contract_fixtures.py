"""교차언어 계약 적합성 — 골든 픽스처(fixtures/proto-v1/messages.json)를 Python 모델로 라운드트립.

iPad(Swift) 측 ios/Tests/.../ContractFixturesTests.swift가 같은 파일을 검증한다.
드리프트(키명·enum값·null 생략) 발생 시 한쪽이 깨진다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from trash_sorter import protocol as p

_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "proto-v1" / "messages.json"

_TYPES = {
    "DeviceInfo": p.DeviceInfo,
    "Status": p.Status,
    "PhotoReady": p.PhotoReady,
    "ClassificationResult": p.ClassificationResult,
    "Command": p.Command,
    "CommandAck": p.CommandAck,
}


def _load_cases() -> list[dict]:
    data = json.loads(_FIXTURE.read_text())
    assert data["proto"] == p.PROTO_VERSION
    return data["cases"]


def test_fixture_file_exists() -> None:
    assert _FIXTURE.is_file(), f"골든 픽스처 없음: {_FIXTURE}"


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: f"{c['type']}:{sorted(c['wire'])}")
def test_roundtrip_matches_wire(case: dict) -> None:
    model_cls = _TYPES[case["type"]]
    wire = case["wire"]
    # 와이어 → 모델 → 와이어. null 생략 규약이므로 재인코드 결과는 원본과 정확히 일치해야 한다.
    model = model_cls.from_json(json.dumps(wire))
    reencoded = json.loads(model.to_json())
    assert reencoded == wire
