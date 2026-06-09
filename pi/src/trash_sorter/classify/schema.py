"""분류 결과 스키마 — Gemini structured output 응답 스키마 + 검증된 데이터 모델.

3분류(pet/can/other)는 iPad/Pi의 WasteCategory와 일치한다(docs/protocol.md §4.1).
"""

from __future__ import annotations

from dataclasses import dataclass

WASTE_CATEGORIES: tuple[str, ...] = ("pet", "can", "other")

ECO_POINTS_MIN = 0
ECO_POINTS_MAX = 100

# Gemini generateContent의 responseSchema(구조화 출력). 이 스키마로만 응답하도록 강제.
# eco_points/recyclable은 iPad 전용 표시·보상 정보(BLE 미전달). docs/protocol.md §4.4/§4.6.
RESPONSE_SCHEMA: dict = {
    "type": "OBJECT",
    "properties": {
        "category": {"type": "STRING", "enum": list(WASTE_CATEGORIES)},
        "description": {"type": "STRING"},
        "confidence": {"type": "NUMBER"},
        "eco_points": {"type": "INTEGER"},
        "recyclable": {"type": "BOOLEAN"},
    },
    "required": ["category", "description", "confidence", "eco_points", "recyclable"],
    "propertyOrdering": ["category", "description", "confidence", "eco_points", "recyclable"],
}


@dataclass(frozen=True)
class Classification:
    category: str       # pet | can | other
    description: str    # 한국어 재활용 팁
    confidence: float   # 0.0 ~ 1.0
    eco_points: int     # 탄소절감 에코포인트 0~100 (재활용 불가 일반쓰레기는 0). docs §4.6
    recyclable: bool    # 재활용 가능 여부 (other라도 true면 보상 대상)

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
        try:
            eco_points = int(d.get("eco_points", 0))
        except (TypeError, ValueError):
            eco_points = 0
        eco_points = max(ECO_POINTS_MIN, min(ECO_POINTS_MAX, eco_points))
        recyclable = bool(d.get("recyclable", False))
        # 재활용 불가면 에코포인트는 0으로 강제(보상 산출 일관성). docs §4.6
        if not recyclable:
            eco_points = 0
        return Classification(
            category=category,
            description=str(d.get("description", "")).strip(),
            confidence=confidence,
            eco_points=eco_points,
            recyclable=recyclable,
        )

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "description": self.description,
            "confidence": self.confidence,
            "eco_points": self.eco_points,
            "recyclable": self.recyclable,
        }
