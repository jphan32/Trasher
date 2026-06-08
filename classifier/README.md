# trash-classifier (Gemini 분류 프록시)

쓰레기 이미지를 **3종(pet/can/other)** 으로 분류하고 **재활용 팁**을 함께 반환하는 HTTP 프록시.
[Gemini 3.5 Flash](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-5-flash)
의 **structured output**(responseSchema)으로 확실한 스키마를 보장한다.

## 왜 별도 서비스인가

분류 API는 **GCP 서비스 계정 키**(서버 자격증명)를 쓴다. 이 키를 배포되는 iPad 앱에 넣는 것은
보안상 부적절하므로, 키를 보유한 이 프록시가 Gemini를 호출하고 **iPad는 프록시 엔드포인트만 호출**한다.
(BLE 계약은 불변 — Pi에는 여전히 3분류만 전달, 팁은 iPad 내부에서 표시.)

## API

```
POST /classify   # multipart 'image' 또는 raw 이미지 본문
  → 200 {"category":"pet|can|other","description":"<재활용 팁(한국어)>","confidence":0.0~1.0}
  → 400 이미지 없음 / 502 Gemini 오류
GET  /health     → {"ok":true,"model":"gemini-3.5-flash"}
```

## 실행

```bash
cd classifier
uv sync
CLASSIFIER_CREDENTIALS=../secret/gemini-api-key.json uv run trash-classifier   # :8090

# 또는 .env.example 복사 후 환경변수 설정
```

부스 배포: 인터넷 + 키가 있는 곳(예: Pi)에서 실행. iPad의 `RemoteClassificationConfig.endpoint`를
이 서비스의 `…/classify`로 설정한다.

## 개발/테스트

```bash
uv run pytest -q       # mock 기반(네트워크 불필요)
uv run ruff check .
uv run mypy

# 실 Gemini 라이브 스모크(opt-in)
CLASSIFIER_LIVE=1 CLASSIFIER_CREDENTIALS=../secret/gemini-api-key.json \
  uv run --with pillow pytest tests/test_live.py -q
```

## 구조

- `prompts.toml` — 시스템 지침 + 분류 프롬프트(코드와 분리, 현장 튜닝)
- `schema.py` — 3분류 enum + responseSchema + 검증된 `Classification`
- `gemini.py` — SA 인증 + generateContent(structured output) 호출
- `server.py` — Flask 프록시
