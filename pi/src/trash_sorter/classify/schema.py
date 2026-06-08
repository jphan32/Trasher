"""분류 결과 스키마 — Gemini structured output 응답 스키마 + 검증된 데이터 모델.

3분류(pet/can/other)는 iPad/Pi의 WasteCategory와 일치한다(docs/protocol.md §4.1).
"""

from __future__ import annotations

from dataclasses import dataclass

WASTE_CATEGORIES: tuple[str, ...] = ("pet", "can", "other")

# Gemini generateContent의 responseSchema(구조화 출력). 이 스키마로만 응답하도록 강제.
RESPONSE_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "category": {"type": "STRING", "enum": list(WASTE_CATEGORIES)},
        "description": {"type": "STRING"},
        "confidence": {"type": "NUMBER"},
    },
    "required": ["category", "description", "confidence"],
    "propertyOrdering": ["category", "description", "confidence"],
}


@dataclass(frozen=True)
class Classification:
    category: str       # pet | can | other
    description: str    # 한국어 재활용 팁
    confidence: float   # 0.0 ~ 1.0

    @staticmethod
    def from_response(d: dict) -> Classification:
        """Gemini 응답 dict를 검증·정규화. 미지 카테고리는 안전 기본값 other."""
        category = str(d.get("category", "")).strip().lower()
        if category not in WASTE_CATEGORIES:
            category = "other"
        try:
            confidence = float(d.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        return Classification(
            category=category,
            description=str(d.get("description", "")).strip(),
            confidence=confidence,
        )

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "description": self.description,
            "confidence": self.confidence,
        }
