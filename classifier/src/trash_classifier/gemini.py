"""Gemini 분류 클라이언트 — Generative Language API + structured output.

서비스 계정(OAuth)로 인증해 ``generateContent``를 호출하고, responseSchema로 강제된
구조화 JSON({category, description, confidence})을 받는다.

세션은 주입 가능(테스트는 fake, 실서비스는 google-auth AuthorizedSession이 토큰 자동 갱신).
"""

from __future__ import annotations

import base64
import json
from typing import Any, Protocol, cast

from .config import Settings
from .prompts import Prompts
from .schema import RESPONSE_SCHEMA, Classification


class ClassificationError(RuntimeError):
    """Gemini 호출/응답 파싱 실패."""


class _Response(Protocol):
    status_code: int
    text: str

    def json(self) -> Any: ...


class _Session(Protocol):
    def post(self, url: str, json: Any, timeout: float) -> _Response: ...


class GeminiClassifier:
    def __init__(
        self, settings: Settings, prompts: Prompts, *, session: _Session | None = None
    ) -> None:
        self._s = settings
        self._p = prompts
        self._session = session

    def _get_session(self) -> _Session:
        session = self._session
        if session is None:
            from google.auth.transport.requests import AuthorizedSession
            from google.oauth2 import service_account

            creds = service_account.Credentials.from_service_account_file(
                self._s.credentials_path, scopes=[self._s.scope]
            )
            session = cast("_Session", AuthorizedSession(creds))
            self._session = session
        return session

    def classify(self, image_bytes: bytes, mime: str = "image/jpeg") -> Classification:
        url = f"{self._s.api_base}/models/{self._s.model}:generateContent"
        resp = self._get_session().post(url, json=self._build_body(image_bytes, mime),
                                        timeout=self._s.timeout_s)
        if resp.status_code != 200:
            raise ClassificationError(f"Gemini {resp.status_code}: {resp.text[:300]}")
        text = self._extract_text(resp.json())
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as e:
            raise ClassificationError(f"구조화 출력 JSON 파싱 실패: {text[:200]}") from e
        return Classification.from_response(payload)

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
                "temperature": self._s.temperature,
            },
        }

    @staticmethod
    def _extract_text(data: Any) -> str:
        try:
            return str(data["candidates"][0]["content"]["parts"][0]["text"])
        except (KeyError, IndexError, TypeError) as e:
            # 안전성 차단/빈 응답 등
            raise ClassificationError(f"Gemini 응답에 후보가 없음: {str(data)[:200]}") from e
