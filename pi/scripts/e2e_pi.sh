#!/usr/bin/env bash
# 라이브 Pi에 HTTP E2E용 mock-모드 서버를 경량 기동/정지한다.
# 서보·벨트·BLE·카메라·Gemini 없이 사진/분류 HTTP 계약만 띄운다(TRASH_MOCK=1, 빈 Gemini 키).
#
# 사용법(저장소 루트에서):
#   pi/scripts/e2e_pi.sh up       # 소스 동기화 → uv venv/sync → 사진 시드 → mock 서버 기동
#   pi/scripts/e2e_pi.sh down     # 서버 정지 + 정리
#   pi/scripts/e2e_pi.sh status   # 포트/프로세스 확인
#
# 그 뒤 Mac에서:  cd pi && TRASH_PI_SEEDED_CYCLE=424242 uv run pytest -m e2e
#
# 접속 주소 단일 원천 = SSH 별칭 rp4b(~/.ssh/config). 주소가 바뀌면 rp4b만 고치면 된다.
# /opt·systemd는 건드리지 않는다 — 홈 스크래치 디렉터리만 쓰며 `down`으로 완전 가역.
set -euo pipefail

SSH_HOST="${E2E_SSH_HOST:-rp4b}"
PORT="${TRASH_PI_PORT:-8080}"
CYCLE="${TRASH_PI_SEEDED_CYCLE:-424242}"
REMOTE_DIR="trash-e2e"        # ~/trash-e2e (홈 상대 — sudo 불필요)
PHOTO_DIR="trash-e2e-photos"  # ~/trash-e2e-photos
PIDFILE="trash-e2e.pid"       # ~/trash-e2e.pid
LOGFILE="trash-e2e.log"       # ~/trash-e2e.log
# 최소 유효 JPEG(SOI + JFIF APP0 + EOI)의 base64 — 바이너리 안전 전송용.
SEED_B64="/9j/4AAQSkZJRgABAQAAAQABAAD/2Q=="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PI_DIR="$(dirname "$SCRIPT_DIR")"

resolve_host() { ssh -G "$SSH_HOST" 2>/dev/null | awk '/^hostname /{print $2; exit}'; }

cmd_up() {
  echo "[e2e] 타깃: $SSH_HOST → $(resolve_host)  포트:$PORT  시드 cycle:$CYCLE"

  echo "[e2e] 1/4 소스 동기화 → $SSH_HOST:~/$REMOTE_DIR"
  rsync -az --delete \
    "$PI_DIR/pyproject.toml" "$PI_DIR/uv.lock" "$PI_DIR/src" \
    "$SSH_HOST:$REMOTE_DIR/"

  echo "[e2e] 2/4 venv + 의존성(uv sync — 크로스플랫폼만, 하드웨어 extras 제외)"
  ssh "$SSH_HOST" "cd $REMOTE_DIR && ~/.local/bin/uv venv >/dev/null && \
    ~/.local/bin/uv sync >/dev/null 2>&1 && test -x .venv/bin/trash-sorter && echo '  venv ok'"

  echo "[e2e] 3/4 사진 시드 → ~/$PHOTO_DIR/$CYCLE.jpg"
  ssh "$SSH_HOST" "mkdir -p ~/$PHOTO_DIR && echo '$SEED_B64' | base64 -d > ~/$PHOTO_DIR/$CYCLE.jpg && \
    echo \"  \$(wc -c < ~/$PHOTO_DIR/$CYCLE.jpg) bytes\""

  echo "[e2e] 4/4 mock 서버 기동(:$PORT)"
  # uv 래퍼가 아닌 설치된 콘솔 스크립트를 직접 실행 → 단일 프로세스(uv 자식 python 오펀 방지).
  ssh "$SSH_HOST" "bash -lc '
    cd ~/$REMOTE_DIR && rm -f ~/$LOGFILE
    nohup env TRASH_MOCK=1 TRASH_PHOTO_DIR=\$HOME/$PHOTO_DIR TRASH_HTTP_PORT=$PORT \
      TRASH_PHOTO_RETENTION=100000 TRASH_HEARTBEAT=3600 TRASH_GEMINI_CREDENTIALS= \
      ./.venv/bin/trash-sorter >~/$LOGFILE 2>&1 </dev/null &
    echo \$! > ~/$PIDFILE; disown || true
  '"

  for _ in $(seq 1 40); do
    if ssh "$SSH_HOST" "ss -tln 2>/dev/null | grep -q :$PORT"; then
      echo "[e2e] 서버 LISTEN :$PORT ✓"
      echo "[e2e] 다음:  cd pi && TRASH_PI_SEEDED_CYCLE=$CYCLE uv run pytest -m e2e"
      return 0
    fi
    sleep 0.5
  done
  echo "[e2e] ✗ 서버 미기동. 로그(마지막 30줄):" >&2
  ssh "$SSH_HOST" "tail -30 ~/$LOGFILE" >&2 || true
  return 1
}

cmd_down() {
  echo "[e2e] 서버 정지 + 정리 ($SSH_HOST)"
  # 단일 프로세스라 pid kill로 충분 + 안전망 pkill([t] 브래킷으로 ssh 셸 자기참조 회피).
  ssh "$SSH_HOST" "bash -lc '
    if [ -f ~/$PIDFILE ]; then
      pid=\$(cat ~/$PIDFILE)
      kill -TERM \"\$pid\" 2>/dev/null || true; sleep 1; kill -KILL \"\$pid\" 2>/dev/null || true
      rm -f ~/$PIDFILE
    fi
    pkill -f \"[t]rash_sorter\" 2>/dev/null || true; sleep 0.3
    if ss -tln 2>/dev/null | grep -q :$PORT; then echo \"  WARN: :$PORT 아직 LISTEN\"; else echo \"  :$PORT closed ✓\"; fi
  '"
}

cmd_status() {
  echo "[e2e] $SSH_HOST → $(resolve_host)  포트:$PORT"
  ssh "$SSH_HOST" "bash -lc '
    printf \"  pidfile: \"; cat ~/$PIDFILE 2>/dev/null || echo none
    ss -tln 2>/dev/null | grep :$PORT || echo \"  nothing on :$PORT\"
    pgrep -af \"[t]rash_sorter\" || echo \"  no trash_sorter proc\"
  '"
}

case "${1:-}" in
  up) cmd_up ;;
  down) cmd_down ;;
  status) cmd_status ;;
  *) echo "사용법: $0 {up|down|status}" >&2; exit 2 ;;
esac
