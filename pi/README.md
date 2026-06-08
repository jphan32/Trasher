# trash-sorter (Raspberry Pi 제어 프로그램)

AI 쓰레기 자동 분류기의 Pi 측. BLE Peripheral + HTTP 사진서버 + 비전(변이검출) + 서보3/벨트1 제어.
계약 문서: [`../docs/protocol.md`](../docs/protocol.md).

## 개발 (macOS/CI) — uv 사용

Python 환경은 **uv**로 관리한다. 하드웨어 의존(picamera2/gpiozero/bless)은 **Linux 전용**이라
설치하지 않고 Mock 구현으로 전 사이클을 테스트한다.

```bash
cd pi
uv sync               # .venv 생성 + 크로스플랫폼 의존성 + dev 도구(PEP 735 그룹)

uv run ruff check .   # 린트
uv run mypy           # 타입체크
uv run pytest -q      # 테스트(전부 mock 기반)
```

## 실기기 (Raspberry Pi)

```bash
uv sync                                # 크로스플랫폼 + dev
uv pip install -r requirements-pi.txt  # picamera2/gpiozero/bless (Linux 전용)
uv run trash-sorter                    # 또는 uv run python -m trash_sorter
```

> 하드웨어 의존성을 `requirements-pi.txt`로 분리한 이유: 해당 sdist가 Linux에서만 빌드되어
> macOS의 uv universal 해석을 깨뜨리기 때문. dev 머신에선 어차피 불필요(Mock 사용).

## 구조

```
src/trash_sorter/
  protocol.py      # GATT UUID·enum·JSON 메시지 (docs/protocol.md 동기화)
  config.py        # GPIO핀·서보각·타이밍·임계값 (env override)
  state.py         # 상태머신 (순수 로직, 하드웨어 비의존)
  hardware/        # 서보3/벨트1: 인터페이스 + Mock/gpiozero + sort 시퀀스
  vision/          # 카메라 + 변이검출: 인터페이스 + Mock/picamera2
  ble/             # BLE Peripheral: 인터페이스 + Mock/bless
  classify/        # Gemini 분류(structured output) + Mock, prompts.toml
  web/             # 사진 HTTP 서버 + POST /classify/{cycle}
  app.py           # 오케스트레이터 (전 구성요소 결선 + 사이클 루프)
  sim.py           # 시뮬레이션 모드(--simulate), 비전 튜닝(--tune)
  factory.py       # 플랫폼 분기 조립
```

설계 원칙: 모든 하드웨어/비전/BLE는 **인터페이스 뒤의 Mock**으로 macOS에서 검증 가능. 실기기 구현은
플랫폼에서만 import. 자세한 개발 사이클은 [`../docs/dev-cycle.md`](../docs/dev-cycle.md).

## 배포 (Raspberry Pi, systemd)

부스 무인 기동: 저장소를 Pi에 복사한 뒤,

```bash
sudo bash pi/deploy/install.sh   # 코드→/opt/trash-sorter, uv sync + 하드웨어 extras, systemd 등록·시작
sudo nano /etc/trash-sorter.env  # 현장 튜닝값(핀/임계값/IP) — deploy/trash-sorter.env.example 참조
sudo systemctl restart trash-sorter
journalctl -u trash-sorter -f    # 로그
```

- 죽으면 자동 재시작(`Restart=always`), 부팅 시 자동 기동(`enable`).
- 하드웨어 없이 점검: `uv run trash-sorter --simulate` (사이클 로깅) / `uv run trash-sorter --tune <frames_dir>` (임계값 보정).
