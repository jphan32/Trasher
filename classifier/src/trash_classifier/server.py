"""Flask 분류 프록시 — iPad가 호출하는 HTTP 엔드포인트.

POST /classify  (multipart 'image' 또는 raw 본문) → {category, description, confidence}
GET  /health
"""

from __future__ import annotations

from flask import Flask, Response, jsonify, request

from .config import Settings
from .gemini import ClassificationError, GeminiClassifier


def create_app(classifier: GeminiClassifier, settings: Settings) -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health() -> Response:
        return jsonify({"ok": True, "model": settings.model})

    @app.post("/classify")
    def classify() -> tuple[Response, int] | Response:
        file = request.files.get("image")
        if file is not None:
            data = file.read()
            mime = file.mimetype or "image/jpeg"
        else:
            data = request.get_data()
            mime = request.content_type or "image/jpeg"
        if not data:
            return jsonify({"error": "이미지가 비어 있습니다"}), 400
        try:
            result = classifier.classify(data, mime=mime)
        except ClassificationError as e:
            return jsonify({"error": str(e)}), 502
        return jsonify(result.to_dict())

    return app
