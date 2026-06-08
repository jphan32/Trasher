"""테스트 공용 — Gemini 세션 fake + 설정/프롬프트 더미."""

from __future__ import annotations

import json
from typing import Any

from trash_classifier.config import Settings
from trash_classifier.prompts import Prompts


class FakeResp:
    def __init__(self, status: int, payload: Any) -> None:
        self.status_code = status
        self._payload = payload
        self.text = json.dumps(payload) if isinstance(payload, dict | list) else str(payload)

    def json(self) -> Any:
        return self._payload


class FakeSession:
    def __init__(self, resp: FakeResp) -> None:
        self.resp = resp
        self.calls: list[tuple] = []

    def post(self, url: str, json: Any = None, timeout: float = 0) -> FakeResp:
        self.calls.append((url, json, timeout))
        return self.resp


def gemini_ok(
    category: str = "can", desc: str = "캔은 비우고 헹궈 배출하세요.", conf: float = 0.9
) -> dict:
    """structured output 성공 응답(candidates[0].content.parts[0].text = JSON)."""
    text = json.dumps({"category": category, "description": desc, "confidence": conf})
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def dummy_settings() -> Settings:
    return Settings(
        credentials_path="x", model="gemini-3.5-flash", host="127.0.0.1",
        port=8090, timeout_s=5.0, temperature=0.0,
    )


def dummy_prompts() -> Prompts:
    return Prompts(system_instruction="sys", classify_prompt="분류해줘")
