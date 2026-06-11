#!/usr/bin/env bash
# Raspberry Pi 배포 설치 — 코드 복사 → 의존성 설치 → systemd 서비스 등록.
# 사용법(저장소 루트에서): sudo bash pi/deploy/install.sh
#
# 실행 사용자(서비스가 돌 계정)는 sudo 호출자($SUDO_USER)로 자동 감지한다.
# 'pi' 하드코딩 금지 — 현장 Pi는 커스텀 사용자(예: jphan32)일 수 있다.
set -euo pipefail

APP_DIR=/opt/trash-sorter
SERVICE=trash-sorter.service
ENV_DST=/etc/trash-sorter.env

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PI_DIR="$(dirname "$SCRIPT_DIR")"

if [[ $EUID -ne 0 ]]; then
  echo "root 권한이 필요합니다: sudo bash pi/deploy/install.sh" >&2
  exit 1
fi

# 서비스 실행 사용자 — sudo 호출자(없으면 logname). root로는 서비스를 돌리지 않는다.
RUN_USER="${SUDO_USER:-$(logname 2>/dev/null || true)}"
if [[ -z "$RUN_USER" || "$RUN_USER" == "root" ]]; then
  echo "서비스 실행 사용자를 정할 수 없습니다. RUN_USER=<user> sudo -E bash ... 로 지정하세요." >&2
  exit 1
fi
RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"

# uv는 보통 사용자 홈(~/.local/bin)에 설치됨 — root PATH엔 없으므로 직접 찾는다.
UV="$RUN_HOME/.local/bin/uv"
[[ -x "$UV" ]] || UV="$(command -v uv 2>/dev/null || true)"
if [[ -z "$UV" || ! -x "$UV" ]]; then
  echo "uv를 찾을 수 없습니다($RUN_USER). 설치: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
  exit 1
fi
echo "실행 사용자: $RUN_USER | uv: $UV"

echo "[1/5] 코드 복사 → $APP_DIR (소유자 $RUN_USER)"
mkdir -p "$APP_DIR"
cp -rf "$PI_DIR"/{pyproject.toml,uv.lock,requirements-pi.txt,src} "$APP_DIR"/
# secret/(Gemini 키)이 있으면 함께 복사(없으면 건너뜀 — gitignore라 저장소엔 없음)
[[ -d "$PI_DIR/secret" ]] && cp -rf "$PI_DIR/secret" "$APP_DIR"/ || true
chown -R "$RUN_USER:$RUN_USER" "$APP_DIR"

echo "[2/5] 의존성 설치(system-site venv + uv sync --inexact + Pi 하드웨어 extras) — $RUN_USER로 실행"
# venv/의존성은 서비스 실행 사용자로 생성해야 소유·권한이 맞는다(root venv 금지).
# 시스템 Python 3.13 + --system-site-packages: apt picamera2/libcamera import용(docs §4/§10).
# --inexact: requirements-pi.txt 하드웨어 의존(gpiozero/opencv)을 prune하지 않게.
sudo -u "$RUN_USER" -H bash -lc "cd '$APP_DIR' && '$UV' venv --python /usr/bin/python3 --system-site-packages && '$UV' sync --inexact && '$UV' pip install -r requirements-pi.txt"

echo "[3/5] 환경파일 설치(없을 때만): $ENV_DST"
if [[ ! -f "$ENV_DST" ]]; then
  cp "$SCRIPT_DIR/trash-sorter.env.example" "$ENV_DST"
  echo "  → $ENV_DST 생성됨. 현장값(특히 TRASH_GEMINI_CREDENTIALS)으로 편집하세요."
else
  echo "  → 이미 존재, 유지."
fi

echo "[4/5] systemd 서비스 등록(User/Group=$RUN_USER 주입)"
# .service의 User/Group을 실제 실행 사용자로 치환해 설치('pi' 하드코딩 회피).
sed -e "s/^User=.*/User=$RUN_USER/" -e "s/^Group=.*/Group=$RUN_USER/" \
    "$SCRIPT_DIR/$SERVICE" > "/etc/systemd/system/$SERVICE"
systemctl daemon-reload
systemctl enable "$SERVICE"

echo "[5/5] 서비스 시작"
systemctl restart "$SERVICE"

echo
echo "완료. 상태: systemctl status trash-sorter | 로그: journalctl -u trash-sorter -f"
echo "참고: 서보는 lgpio 기본 팩토리로 동작(Trixie엔 pigpio 데몬 없음). PWMSoftwareFallback 경고는 무시."
