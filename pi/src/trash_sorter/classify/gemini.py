"""Gemini 분류 클라이언트 — Generative Language API + structured output.

Pi가 로컬 사진(이미지 바이트)을 읽어 Gemini 3.5 Flash로 3분류 + 재활용 팁을 받는다.
키가 없으면(dev/sim/무인터넷) MockClassifier로 대체된다.
"""

from __future__ import annotations

import base64
import itertools
import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, cast

from .config import ClassifierConfig, load_classifier_config
from .prompts import Prompts, load_prompts
from .schema import RESPONSE_SCHEMA, Classification


class ClassificationError(RuntimeError):
    """Gemini 호출/응답 파싱 실패."""


class Classifier(Protocol):
    def classify(self, image_bytes: bytes, mime: str = "image/jpeg") -> Classification: ...


class _Response(Protocol):
    status_code: int
    text: str

    def json(self) -> Any: ...


class _Session(Protocol):
    def post(self, url: str, json: Any, timeout: float) -> _Response: ...


_TRANSIENT_STATUS = frozenset({429, 500, 502, 503, 504})


class GeminiClassifier:
    def __init__(
        self,
        config: ClassifierConfig,
        prompts: Prompts,
        *,
        session: _Session | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._c = config
        self._p = prompts
        self._session = session
        self._lock = threading.Lock()  # ThreadingHTTPServer 워커 동시호출 직렬화
        if sleep is None:
            import time

            sleep = time.sleep
        self._sleep = sleep

    def _get_session(self) -> _Session:
        # lazy-init만 짧게 직렬화한다. 백오프 sleep을 포함한 재시도 루프를 락 밖에 두어,
        # 한 요청의 재시도 대기가 다른 요청을 막지 않게 한다. AuthorizedSession은 토큰 갱신을
        # 내부적으로 잠그고, 부스는 단일 사용자(동시 분류 사실상 없음)라 동시 post는 안전.
        with self._lock:
            if self._session is None:
                from google.auth.transport.requests import AuthorizedSession
                from google.oauth2 import service_account

                creds = service_account.Credentials.from_service_account_file(
                    self._c.credentials_path, scopes=[self._c.scope]
                )
                self._session = cast("_Session", AuthorizedSession(creds))
            return self._session

    def classify(self, image_bytes: bytes, mime: str = "image/jpeg") -> Classification:
        url = f"{self._c.api_base}/models/{self._c.model}:generateContent"
        body = self._build_body(image_bytes, mime)
        resp = self._post_with_retry(url, body)  # 락 밖 — 백오프 sleep이 다른 요청을 막지 않음
        text = self._extract_text(resp.json())
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            raise ClassificationError(f"구조화 출력 JSON 파싱 실패: {text[:200]}") from e
        return Classification.from_response(payload)

    def _post_with_retry(self, url: str, body: dict) -> _Response:
        """transient(429/5xx/네트워크) 오류에 백오프 재시도. 그 외 상태는 즉시 실패.

        실제 HTTP 호출(session.post)만 락으로 직렬화해 requests.Session 동시 사용을 보호하고,
        백오프 sleep은 락 밖에서 수행해 한 요청의 재시도 대기가 다른 요청을 막지 않게 한다(m3).
        """
        session = self._get_session()  # 자격증명 오류는 transient 아님 → 즉시 전파
        for attempt in range(self._c.max_retries + 1):
            is_last = attempt == self._c.max_retries
            try:
                with self._lock:
                    resp = session.post(url, json=body, timeout=self._c.timeout_s)
            except Exception as e:  # noqa: BLE001 - 네트워크 오류는 transient로 재시도
                if is_last:
                    raise ClassificationError(f"네트워크 오류: {type(e).__name__}") from e
                self._sleep(self._c.retry_backoff_s * (attempt + 1))
                continue
            if resp.status_code == 200:
                return resp
            if resp.status_code not in _TRANSIENT_STATUS:
                raise ClassificationError(f"Gemini {resp.status_code}: {resp.text[:300]}")
            if is_last:
                raise ClassificationError(
                    f"Gemini {resp.status_code} 재시도 소진: {resp.text[:160]}"
                )
            self._sleep(self._c.retry_backoff_s * (attempt + 1))
        raise ClassificationError("재시도 소진")  # 도달 불가(루프가 항상 return/raise)

    def _build_body(self, image_bytes: bytes, mime: str) -> dict:
        b64 = base64.b64encode(image_bytes).decode()
        return {
            "system_instruction": {"parts": [{"text": self._p.system_instruction}]},
            "contents": [
                {
                    "parts": [
                        {"inline_data": {"mime_type": mime, "data": b64}},
                        {"text": self._p.classify_prompt},
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": RESPONSE_SCHEMA,
                "temperature": self._c.temperature,
            },
        }

    @staticmethod
    def _extract_text(data: Any) -> str:
        try:
            return str(data["candidates"][0]["content"]["parts"][0]["text"])
        except (KeyError, IndexError, TypeError) as e:
            raise ClassificationError(f"Gemini 응답에 후보가 없음: {str(data)[:200]}") from e


class MockClassifier:
    """키/인터넷 없는 dev/sim용 — 4가지를 매칭 팁·에코포인트와 함께 회전.

    보상 티어를 모두 시연: pet(60→사탕2), can(55→사탕2),
    other-재활용 유리(30→사탕1), other-일반쓰레기(0→사탕0). docs §4.6.
    """

    # (category, tip, eco_points, recyclable)
    _ITEMS = [
        ("pet", "페트병은 라벨을 떼고 비운 뒤 압착해 투명 페트 전용함에 배출해요.", 60, True),
        ("can", "캔은 내용물을 비우고 헹군 뒤 납작하게 펴서 캔류로 배출해요.", 55, True),
        ("other", "유리병은 색깔별로 모아 유리류 전용함에 배출해요.", 30, True),
        ("other", "재활용이 어려운 일반 쓰레기는 종량제 봉투에 배출해요.", 0, False),
    ]

    def __init__(self) -> None:
        self._cycle = itertools.cycle(self._ITEMS)
        self._lock = threading.Lock()  # itertools.cycle은 스레드 안전하지 않음

    def classify(self, image_bytes: bytes, mime: str = "image/jpeg") -> Classification:
        with self._lock:
            category, tip, eco, recyclable = next(self._cycle)
        return Classification(
            category=category,
            description=tip,
            confidence=0.95,
            eco_points=eco,
            recyclable=recyclable,
        )


def build_classifier(config: ClassifierConfig | None = None) -> Classifier:
    """키가 있으면 GeminiClassifier, 없으면 MockClassifier."""
    config = config or load_classifier_config()
    if config.credentials_path and Path(config.credentials_path).is_file():
        return GeminiClassifier(config, load_prompts())
    return MockClassifier()
