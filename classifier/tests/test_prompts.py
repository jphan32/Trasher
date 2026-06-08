"""prompts.toml 로딩 테스트."""

from __future__ import annotations

from trash_classifier.prompts import load_prompts


def test_load_prompts_has_content() -> None:
    p = load_prompts()
    assert p.system_instruction
    assert p.classify_prompt
    # 3분류가 시스템 지침에 명시돼 있어야 함
    for cat in ("pet", "can", "other"):
        assert cat in p.system_instruction
