"""prompts.toml 로더 — 시스템 지침 + 분류 프롬프트를 코드와 분리."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parents[2] / "prompts.toml"


@dataclass(frozen=True)
class Prompts:
    system_instruction: str
    classify_prompt: str


def load_prompts(path: str | Path | None = None) -> Prompts:
    p = Path(path) if path else _DEFAULT
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    return Prompts(
        system_instruction=data["system"]["instruction"].strip(),
        classify_prompt=data["classify"]["prompt"].strip(),
    )
