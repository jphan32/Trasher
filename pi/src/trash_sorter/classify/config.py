"""분류기 설정. env(``TRASH_CLASSIFIER_*`` / ``CLASSIFIER_*``)로 override."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env(*names: str, default: str = "") -> str:
    for n in names:
        v = os.environ.get(n)
        if v is not None:
            return v
    return default


@dataclass(frozen=True)
class ClassifierConfig:
    credentials_path: str   # GCP 서비스 계정 JSON 키 경로(없으면 Mock 분류기 사용)
    model: str
    timeout_s: float
    temperature: float
    max_retries: int = 2          # transient 오류(429/5xx/네트워크) 재시도 횟수
    retry_backoff_s: float = 0.5  # 백오프 기준(attempt마다 ×(attempt+1))
    api_base: str = "https://generativelanguage.googleapis.com/v1beta"
    scope: str = "https://www.googleapis.com/auth/generative-language"


def load_classifier_config() -> ClassifierConfig:
    return ClassifierConfig(
        credentials_path=_env("TRASH_GEMINI_CREDENTIALS", "CLASSIFIER_CREDENTIALS", default=""),
        model=_env("TRASH_GEMINI_MODEL", "CLASSIFIER_MODEL", default="gemini-3.5-flash"),
        timeout_s=float(_env("TRASH_GEMINI_TIMEOUT", default="60")),
        temperature=float(_env("TRASH_GEMINI_TEMPERATURE", default="0")),
        max_retries=int(_env("TRASH_GEMINI_RETRIES", default="2")),
        retry_backoff_s=float(_env("TRASH_GEMINI_BACKOFF", default="0.5")),
    )
