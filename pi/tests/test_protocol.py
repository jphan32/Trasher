"""프로토콜 메시지 직렬화/역직렬화 라운드트립 + 문서 동기 검증."""

from __future__ import annotations

import json

from trash_sorter import protocol as p


def test_uuids_share_base() -> None:
    base = p.SERVICE_UUID[8:]
    for uuid in (
        p.CHAR_DEVICE_INFO,
        p.CHAR_STATUS,
        p.CHAR_PHOTO_READY,
        p.CHAR_CLASSIFICATION_RESULT,
        p.CHAR_COMMAND,
        p.CHAR_COMMAND_ACK,
    ):
        assert uuid[8:] == base
    assert p.PROTO_VERSION == 1


def test_categories() -> None:
    assert {c.value for c in p.WasteCategory} == {"pet", "can", "other"}


def test_device_info_roundtrip() -> None:
    di = p.DeviceInfo(fw="0.1.0", ip="192.168.0.5", port=8080)
    out = p.DeviceInfo.from_json(di.to_json())
    assert out == di
    assert json.loads(di.to_json())["proto"] == 1


def test_status_roundtrip_with_optionals() -> None:
    s = p.Status(state=p.PiState.SORTING, cycle=42, seq=7,
                 err=p.ErrorCode.RESULT_TIMEOUT, last_sort=p.WasteCategory.OTHER)
    assert p.Status.from_json(s.to_json()) == s

    s2 = p.Status(state=p.PiState.IDLE, cycle=0, seq=1)
    d = json.loads(s2.to_json())
    assert "err" not in d and "lastSort" not in d  # None은 생략
    assert p.Status.from_json(s2.to_json()) == s2


def test_photo_ready_roundtrip() -> None:
    pr = p.PhotoReady(cycle=42, path="/photos/42.jpg", w=1280, h=720, ts=1696000000)
    assert p.PhotoReady.from_json(pr.to_json()) == pr


def test_classification_result_roundtrip() -> None:
    cr = p.ClassificationResult(
        cycle=42, category=p.WasteCategory.PET, confidence=0.93, raw="PET_bottle"
    )
    assert p.ClassificationResult.from_json(cr.to_json()) == cr


def test_command_and_ack_roundtrip() -> None:
    c = p.Command(cmd=p.CommandType.SORT, id=7, arg="pet")
    assert p.Command.from_json(c.to_json()) == c
    a = p.CommandAck(id=7, ok=True)
    assert p.CommandAck.from_json(a.to_json()) == a
