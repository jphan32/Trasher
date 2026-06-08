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
        session = self._session
        if session is None:
            from google.auth.transport.requests import AuthorizedSession
            from google.oauth2 import service_account

            creds = service_account.Credentials.from_service_account_file(
                self._c.credentials_path, scopes=[self._c.scope]
            )
            session = cast("_Session", AuthorizedSession(creds))
            self._session = session
        return session

    def classify(self, image_bytes: bytes, mime: str = "image/jpeg") -> Classification:
        url = f"{self._c.api_base}/models/{self._c.model}:generateContent"
        body = self._build_body(image_bytes, mime)
        with self._lock:  # 세션 lazy-init 경쟁 + 동시 호출 직렬화
            resp = self._post_with_retry(url, body)
        text = self._extract_text(resp.json())
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            raise ClassificationError(f"구조화 출력 JSON 파싱 실패: {text[:200]}") from e
        return Classification.from_response(payload)

    def _post_with_retry(self, url: str, body: dict) -> _Response:
        """transient(429/5xx/네트워크) 오류에 백오프 재시도. 그 외 상태는 즉시 실패."""
        session = self._get_session()  # 자격증명 오류는 transient 아님 → 즉시 전파
        for attempt in range(self._c.max_retries + 1):
            is_last = attempt == self._c.max_retries
            try:
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
                raise ClassificationError(f"Gemini {resp.status_code} 재시도 소진: {resp.text[:160]}")
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
    """키/인터넷 없는 dev/sim용 — pet/can/other를 매칭 팁과 함께 회전."""

    _ITEMS = [
        ("pet", "페트병은 라벨을 떼고 내용물을 비운 뒤 압착해 투명 페트 전용함에 배출해요."),
        ("can", "캔은 내용물을 비우고 헹군 뒤 납작하게 만들어 캔류로 배출해요."),
        ("other", "재활용이 어려운 일반 쓰레기는 종량제 봉투에 배출해요."),
    ]

    def __init__(self) -> None:
        self._cycle = itertools.cycle(self._ITEMS)
        self._lock = threading.Lock()  # itertools.cycle은 스레드 안전하지 않음

    def classify(self, image_bytes: bytes, mime: str = "image/jpeg") -> Classification:
        with self._lock:
            category, tip = next(self._cycle)
        return Classification(category=category, description=tip, confidence=0.95)


def build_classifier(config: ClassifierConfig | None = None) -> Classifier:
    """키가 있으면 GeminiClassifier, 없으면 MockClassifier."""
    config = config or load_classifier_config()
    if config.credentials_path and Path(config.credentials_path).is_file():
        return GeminiClassifier(config, load_prompts())
    return MockClassifier()
