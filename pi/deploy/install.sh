#!/usr/bin/env bash
# Raspberry Pi 배포 설치 — 코드 복사 → 의존성 설치 → systemd 서비스 등록.
# 사용법(저장소 루트에서): sudo bash pi/deploy/install.sh
set -euo pipefail

APP_DIR=/opt/trash-sorter
SERVICE=trash-sorter.service
ENV_DST=/etc/trash-sorter.env

# 저장소 내 pi/ 디렉터리(이 스크립트의 두 단계 상위)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PI_DIR="$(dirname "$SCRIPT_DIR")"

if [[ $EUID -ne 0 ]]; then
  echo "root 권한이 필요합니다: sudo bash pi/deploy/install.sh" >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv가 필요합니다. 설치: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi

echo "[1/5] 코드 복사 → $APP_DIR"
mkdir -p "$APP_DIR"
cp -rf "$PI_DIR"/{pyproject.toml,uv.lock,requirements-pi.txt,src} "$APP_DIR"/

echo "[2/5] 의존성 설치(system-site venv + uv sync + Pi 하드웨어 extras)"
cd "$APP_DIR"
# venv는 apt와 같은 시스템 Python 3.13 + system-site로 만들어 apt picamera2/libcamera를 import.
# (pyenv 등 다른 Python·system-site 미설정 시 import libcamera 실패 — docs/pi-setup.md §4/§10)
uv venv --python /usr/bin/python3 --system-site-packages
uv sync                                   # system-site 설정 보존됨
uv pip install -r requirements-pi.txt     # gpiozero/bless/opencv (picamera2/libcamera는 apt+system-site)

echo "[3/5] 환경파일 설치(없을 때만): $ENV_DST"
if [[ ! -f "$ENV_DST" ]]; then
  cp "$SCRIPT_DIR/trash-sorter.env.example" "$ENV_DST"
  echo "  → $ENV_DST 생성됨. 현장값으로 편집하세요."
else
  echo "  → 이미 존재, 유지."
fi

echo "[4/5] systemd 서비스 등록"
cp "$SCRIPT_DIR/$SERVICE" "/etc/systemd/system/$SERVICE"
systemctl daemon-reload
systemctl enable "$SERVICE"

echo "[5/5] 서비스 시작"
systemctl restart "$SERVICE"

echo
echo "완료. 상태: systemctl status trash-sorter | 로그: journalctl -u trash-sorter -f"
