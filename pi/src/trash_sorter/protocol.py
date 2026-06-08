"""BLE GATT 프로토콜 + 분류 데이터 모델 (Python 측).

단일 진실 공급원은 ``docs/protocol.md``. 이 파일은 그 문서의 §1, §3, §4를 Python 상수/모델로
**수동 동기화**한 것이다. 문서를 바꾸면 이 파일과 iPad(Swift) 측을 함께 갱신한다.

- proto 버전: 1
- 모든 특성 페이로드는 UTF-8 JSON.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

PROTO_VERSION = 1

# --- §1 GATT UUID --------------------------------------------------------------
SERVICE_UUID = "4F520100-7A69-4B43-8E2D-1C9A7F3B0001"
CHAR_DEVICE_INFO = "4F520101-7A69-4B43-8E2D-1C9A7F3B0001"
CHAR_STATUS = "4F520102-7A69-4B43-8E2D-1C9A7F3B0001"
CHAR_PHOTO_READY = "4F520103-7A69-4B43-8E2D-1C9A7F3B0001"
CHAR_CLASSIFICATION_RESULT = "4F520104-7A69-4B43-8E2D-1C9A7F3B0001"
CHAR_COMMAND = "4F520105-7A69-4B43-8E2D-1C9A7F3B0001"
CHAR_COMMAND_ACK = "4F520106-7A69-4B43-8E2D-1C9A7F3B0001"

LOCAL_NAME = "sorter-01"


# --- §4.1 3분류 enum -----------------------------------------------------------
class WasteCategory(StrEnum):
    PET = "pet"      # 페트
    CAN = "can"      # 캔
    OTHER = "other"  # 기타 (안전 기본값/catch-all)


# --- §2 상태 머신 상태 ----------------------------------------------------------
class PiState(StrEnum):
    IDLE = "idle"
    DETECTING = "detecting"
    CAPTURING = "capturing"
    AWAITING_RESULT = "awaiting_result"
    SORTING = "sorting"
    ERROR = "error"
    MAINTENANCE = "maintenance"


# --- §3.5 명령 ----------------------------------------------------------------
class CommandType(StrEnum):
    START = "start"
    STOP = "stop"
    RESET = "reset"
    SORT = "sort"
    BELT = "belt"
    CALIBRATE = "calibrate"
    MAINTENANCE = "maintenance"
    ESTOP = "estop"


# --- §5 에러 코드 --------------------------------------------------------------
class ErrorCode(StrEnum):
    CAMERA_FAIL = "camera_fail"
    MOTOR_FAIL = "motor_fail"
    BELT_JAM = "belt_jam"
    RESULT_TIMEOUT = "result_timeout"
    ESTOPPED = "estopped"
    INTERNAL = "internal"


def _drop_none(d: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in d.items() if v is not None}


def _dump(d: dict[str, Any]) -> str:
    """공통 직렬화: null 생략 + 컴팩트 JSON. 모든 메시지의 to_json이 이걸 쓴다."""
    return json.dumps(_drop_none(d), separators=(",", ":"))


# --- §3 특성 페이로드 모델 ------------------------------------------------------
@dataclass(frozen=True)
class DeviceInfo:
    """§3.1 DeviceInfo (Read)."""

    fw: str
    ip: str
    port: int
    name: str = LOCAL_NAME
    proto: int = PROTO_VERSION

    def to_json(self) -> str:
        return _dump(
            {
                "fw": self.fw,
                "proto": self.proto,
                "ip": self.ip,
                "port": self.port,
                "name": self.name,
            }
        )

    @staticmethod
    def from_json(s: str | bytes) -> DeviceInfo:
        d = json.loads(s)
        return DeviceInfo(fw=d["fw"], ip=d["ip"], port=int(d["port"]),
                          name=d.get("name", LOCAL_NAME), proto=int(d.get("proto", PROTO_VERSION)))


@dataclass(frozen=True)
class Status:
    """§3.2 Status (Notify, Read)."""

    state: PiState
    cycle: int
    seq: int
    err: ErrorCode | None = None
    last_sort: WasteCategory | None = None

    def to_json(self) -> str:
        return _dump({
            "state": self.state.value,
            "cycle": self.cycle,
            "seq": self.seq,
            "err": self.err.value if self.err else None,
            "lastSort": self.last_sort.value if self.last_sort else None,
        })

    @staticmethod
    def from_json(s: str | bytes) -> Status:
        d = json.loads(s)
        return Status(
            state=PiState(d["state"]),
            cycle=int(d["cycle"]),
            seq=int(d["seq"]),
            err=ErrorCode(d["err"]) if d.get("err") else None,
            last_sort=WasteCategory(d["lastSort"]) if d.get("lastSort") else None,
        )


@dataclass(frozen=True)
class PhotoReady:
    """§3.3 PhotoReady (Notify)."""

    cycle: int
    path: str
    w: int | None = None
    h: int | None = None
    ts: int | None = None

    def to_json(self) -> str:
        return _dump(
            {"cycle": self.cycle, "path": self.path, "w": self.w, "h": self.h, "ts": self.ts}
        )

    @staticmethod
    def from_json(s: str | bytes) -> PhotoReady:
        d = json.loads(s)
        return PhotoReady(cycle=int(d["cycle"]), path=d["path"],
                          w=d.get("w"), h=d.get("h"), ts=d.get("ts"))


@dataclass(frozen=True)
class ClassificationResult:
    """§3.4 ClassificationResult (Write w/ response). iPad → Pi."""

    cycle: int
    category: WasteCategory
    confidence: float
    raw: str | None = None

    def to_json(self) -> str:
        return _dump({
            "cycle": self.cycle,
            "category": self.category.value,
            "confidence": self.confidence,
            "raw": self.raw,
        })

    @staticmethod
    def from_json(s: str | bytes) -> ClassificationResult:
        d = json.loads(s)
        return ClassificationResult(
            cycle=int(d["cycle"]),
            category=WasteCategory(d["category"]),
            confidence=float(d["confidence"]),
            raw=d.get("raw"),
        )


@dataclass(frozen=True)
class Command:
    """§3.5 Command (Write w/ response). iPad → Pi."""

    cmd: CommandType
    id: int
    arg: str | None = None

    def to_json(self) -> str:
        return _dump({"cmd": self.cmd.value, "arg": self.arg, "id": self.id})

    @staticmethod
    def from_json(s: str | bytes) -> Command:
        d = json.loads(s)
        return Command(cmd=CommandType(d["cmd"]), id=int(d["id"]), arg=d.get("arg"))


@dataclass(frozen=True)
class CommandAck:
    """§3.6 CommandAck (Notify). Pi → iPad."""

    id: int
    ok: bool
    err: ErrorCode | None = None

    def to_json(self) -> str:
        return _dump({"id": self.id, "ok": self.ok, "err": self.err.value if self.err else None})

    @staticmethod
    def from_json(s: str | bytes) -> CommandAck:
        d = json.loads(s)
        return CommandAck(id=int(d["id"]), ok=bool(d["ok"]),
                          err=ErrorCode(d["err"]) if d.get("err") else None)
