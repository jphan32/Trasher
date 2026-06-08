"""분류 프록시 서비스 엔트리포인트."""

from __future__ import annotations

import logging

from .config import load_settings
from .gemini import GeminiClassifier
from .prompts import load_prompts
from .server import create_app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("trash_classifier")

    settings = load_settings()
    classifier = GeminiClassifier(settings, load_prompts())
    app = create_app(classifier, settings)
    log.info("분류 프록시 시작: :%d (model=%s)", settings.port, settings.model)
    app.run(host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
