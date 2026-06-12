"""런타임 튜닝 설정 관리 — iPad ``PUT /config`` 의 단일 진실(스키마+적용+영속화).

docs/protocol.md §8. 공유 ``Settings`` sub-config를 **in-place 변경**하면 매 동작마다
``self._s.<section>.<attr>`` 를 live로 읽는 소비자(오케스트레이터·서보·벨트)가 재시작 없이 즉시
반영한다(HOT). ``TUNABLES`` = 노출 필드 **화이트리스트(=계약)**. ``web/photo_server`` 의 GET/PUT
핸들러가 이 매니저를 호출한다.

영속화 모델: 파일에는 **운영자가 바꾼 키만(delta)** 저장하고, 기동 시 env 기본값 **위에 overlay**
(저장값 우선)한다. 손대지 않은 필드는 계속 env가 통제한다(env=배포 기본, 파일=운영자 오버라이드).
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from .config import Settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Tunable:
    """노출 튜닝 필드 1개. ``section.attr`` 로 위치, [vmin,vmax]·step·label·unit 메타를 담는다."""

    key: str
    section: str  # Settings 속성명: servo/belt/vision/timing/display
    attr: str  # 해당 sub-config 속성명
    label: str
    unit: str
    vmin: float
    vmax: float
    step: float

    def read(self, settings: Settings) -> float:
        return float(getattr(getattr(settings, self.section), self.attr))

    def clamp(self, value: float) -> float:
        return max(self.vmin, min(self.vmax, value))

    def apply(self, settings: Settings, value: float) -> float:
        """[vmin,vmax]로 clamp 후 공유 sub-config에 in-place 대입. clamp된 실제 적용값 반환."""
        clamped = self.clamp(value)
        setattr(getattr(settings, self.section), self.attr, clamped)
        return clamped

    def to_field(self, settings: Settings) -> dict:
        return {
            "key": self.key,
            "section": self.section,
            "label": self.label,
            "unit": self.unit,
            "type": "float",
            "value": self.read(settings),
            "min": self.vmin,
            "max": self.vmax,
            "step": self.step,
        }


# 노출 튜닝 필드(=계약). docs/protocol.md §8.3 표와 iOS PiConfig와 **수동 동기화**.
# 전부 HOT(매 동작 live read 또는 motion은 threshold_provider). 핀·해상도 등 REINIT는 미노출.
TUNABLES: tuple[Tunable, ...] = (
    Tunable("belt_run_seconds", "belt", "run_seconds",
            "벨트 구동 시간", "s", 0.5, 15.0, 0.1),
    Tunable("servo_speed", "servo", "speed",
            "서보 구동 세기", "", 0.05, 1.0, 0.05),
    Tunable("servo_travel_s", "servo", "travel_s",
            "서보 이동 시간", "s", 0.1, 3.0, 0.1),
    Tunable("servo_rehome_s", "servo", "rehome_s",
            "서보 재시팅 시간", "s", 0.2, 5.0, 0.1),
    Tunable("vision_settle_seconds", "vision", "settle_seconds",
            "정지 인정 시간", "s", 0.0, 5.0, 0.1),
    Tunable("vision_detect_max_seconds", "vision", "detect_max_seconds",
            "최대 감지 시간", "s", 1.0, 30.0, 0.5),
    Tunable("vision_motion_threshold", "vision", "motion_threshold",
            "모션 감지 임계값", "", 0.001, 0.5, 0.001),
    Tunable("result_timeout_s", "timing", "result_timeout_s",
            "결과 대기 타임아웃", "s", 3.0, 60.0, 1.0),
    Tunable("heartbeat_period_s", "timing", "heartbeat_period_s",
            "하트비트 주기", "s", 0.5, 5.0, 0.5),
    Tunable("display_min_interval_s", "display", "min_interval_s",
            "OLED 갱신 간격", "s", 0.1, 5.0, 0.1),
)

_BY_KEY: dict[str, Tunable] = {t.key: t for t in TUNABLES}


class ConfigError(ValueError):
    """``PUT /config`` 잘못된 입력(알 수 없는 키·비수치 값). 핸들러가 400으로 매핑."""


def _is_number(raw: object) -> bool:
    # bool은 int 서브클래스라 명시적으로 배제(True/False를 1/0으로 잘못 받지 않게).
    return not isinstance(raw, bool) and isinstance(raw, (int, float))


class ConfigManager:
    """공유 ``Settings`` 의 튜닝 필드를 조회/적용/영속화. 스레드세이프(HTTP 스레드 ↔ 메인 루프)."""

    def __init__(self, settings: Settings, *, persist_path: str | Path | None = None) -> None:
        self._s = settings
        self._lock = threading.Lock()
        self._path = Path(persist_path) if persist_path else None
        # 운영자 오버라이드(파일에 저장되는 delta). load_persisted/apply가 채운다.
        self._overrides: dict[str, float] = {}

    # --- 조회 -------------------------------------------------------------
    def snapshot(self) -> dict:
        """현재 값 + 메타데이터(스키마). ``GET /config`` 응답. docs/protocol.md §8.1."""
        with self._lock:
            return {"fw": self._s.fw_version, "fields": [t.to_field(self._s) for t in TUNABLES]}

    # --- 적용 -------------------------------------------------------------
    def apply(self, changes: dict) -> dict:
        """변경분만 검증·clamp·in-place 적용·영속화. 반환 ``{ok, applied:{key:clamped}, persisted}``

        알 수 없는 키·비수치 값이 **하나라도** 있으면 ``ConfigError``(전체 거부, 부분 적용 없음).
        ``persisted``=영속 저장 성공 여부(파일 미설정/성공=True, 디스크 실패=False). §8.2.
        """
        if not isinstance(changes, dict):
            raise ConfigError("body must be a JSON object")
        # 1) 전량 검증(부분 적용 방지) — 적용 전에 모두 통과해야 한다.
        validated: list[tuple[Tunable, float]] = []
        for key, raw in changes.items():
            tunable = _BY_KEY.get(key)
            if tunable is None:
                raise ConfigError(f"unknown field: {key}")
            if not _is_number(raw):
                raise ConfigError(f"{key} must be a number")
            validated.append((tunable, float(raw)))
        # 2) 적용 + 오버라이드 갱신 + 영속화(락)
        applied: dict[str, float] = {}
        with self._lock:
            for tunable, value in validated:
                clamped = tunable.apply(self._s, value)
                applied[tunable.key] = clamped
                self._overrides[tunable.key] = clamped
            persisted = self._persist_locked()
        # persisted=False ⇒ 파일 저장 실패(메모리엔 적용됨) → iPad가 '재시작 시 소실' 경고. §8.2.
        return {"ok": True, "applied": applied, "persisted": persisted}

    # --- 영속화 -----------------------------------------------------------
    def load_persisted(self) -> dict[str, float]:
        """기동 시 저장된 오버라이드를 env 기본값 **위에 overlay**. 반환: 적용된 ``{key:clamped}``.

        파일 없음/손상/모르는 키·비수치는 **조용히 무시**(graceful — 전방호환·손상 내성). 컴포넌트
        생성 전에 호출해 모든 소비자가 처음부터 저장값을 보게 한다(factory).
        """
        if self._path is None:
            return {}
        try:
            data = json.loads(self._path.read_text())
        except FileNotFoundError:
            return {}  # 첫 부팅(파일 없음)은 정상 — 조용히 env 기본값 사용
        except (OSError, json.JSONDecodeError) as e:
            # 손상/읽기 실패는 비정상 — 부팅은 막지 않되(env 기본값) 눈에 띄게 로깅.
            log.error("런타임 설정 로드 실패(env 기본값으로 부팅): %s", e)
            return {}
        if not isinstance(data, dict):
            log.warning("런타임 설정 파일이 객체가 아님(무시): %s", self._path)
            return {}
        applied: dict[str, float] = {}
        with self._lock:
            for key, raw in data.items():
                tunable = _BY_KEY.get(key)
                if tunable is None or not _is_number(raw):
                    continue  # 모르는 키·비수치는 건너뜀(전방호환)
                clamped = tunable.apply(self._s, float(raw))
                applied[key] = clamped
                self._overrides[key] = clamped
        if applied:
            log.info("런타임 설정 로드(overlay): %s", applied)
        return applied

    def _persist_locked(self) -> bool:
        """오버라이드(delta)를 JSON으로 **원자적** 저장(temp+rename).

        반환: ``True``=저장됨/영속 대상 아님(파일 미설정) · ``False``=저장 실패(메모리엔 적용됨).
        실패는 비치명(부팅·런타임 계속)이나 운영자 조정이 재시작 시 소실되므로 ``error`` 로깅 +
        호출자(apply)가 응답에 실어 iPad가 경고한다(§8.2). 호출자가 ``self._lock`` 보유 가정.
        """
        if self._path is None:
            return True  # 영속 대상 아님(메모리 적용은 의도된 동작) — 실패 아님
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            tmp.write_text(json.dumps(self._overrides, ensure_ascii=False, indent=2))
            tmp.replace(self._path)  # 원자적 교체(부분 기록 노출 방지)
            return True
        except OSError as e:
            log.error("런타임 설정 저장 실패 — 메모리엔 적용됨(재시작 시 소실): %s", e)
            return False
