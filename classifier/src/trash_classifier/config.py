"""분류 서비스 설정. env(``CLASSIFIER_*``)로 override."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    credentials_path: str   # GCP 서비스 계정 JSON 키 경로
    model: str              # Gemini 모델 id
    host: str
    port: int
    timeout_s: float
    temperature: float
    api_base: str = "https://generativelanguage.googleapis.com/v1beta"
    scope: str = "https://www.googleapis.com/auth/generative-language"


def load_settings() -> Settings:
    return Settings(
        credentials_path=os.environ.get("CLASSIFIER_CREDENTIALS", "secret/gemini-api-key.json"),
        model=os.environ.get("CLASSIFIER_MODEL", "gemini-3.5-flash"),
        host=os.environ.get("CLASSIFIER_HOST", "0.0.0.0"),
        port=int(os.environ.get("CLASSIFIER_PORT", "8090")),
        timeout_s=float(os.environ.get("CLASSIFIER_TIMEOUT", "60")),
        temperature=float(os.environ.get("CLASSIFIER_TEMPERATURE", "0")),
    )
