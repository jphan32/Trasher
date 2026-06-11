"""HTTP 전구간 E2E — 실제 엔트리포인트 기동 + 라이브 Pi 계약 검증.

전체 분류 사이클(docs/protocol.md) 중 **Mac↔Pi WiFi HTTP**(사진 GET·분류 POST) 구간을
검증한다. BLE·서보/벨트·카메라·iPad는 실기기 의존이라 여기서 다루지 않는다(trash-3ud/trash-83o).

두 계층(둘 다 ``@pytest.mark.e2e`` — 기본 실행 제외, ``uv run pytest -m e2e``로 실행):

- **Tier A (local):** 실제 ``trash-sorter`` 엔트리포인트를 mock 모드 서브프로세스로 기동
  (``build_app`` → photo_server → device_info → ble → orchestrator 전체 결선을 실제로 탄다).
  시드 사진으로 ``GET /photos``·``POST /classify`` 계약을 검사. 하드웨어 없이 macOS에서 상시 실행.
- **Tier B (live):** 같은 계약을 라이브 Pi(``TRASH_PI_HOST``, 기본 ``192.168.50.164:8080``)에.
  미도달 시 skip. happy-path(사진 200·분류 200)는 ``pi/scripts/e2e_pi.sh up``이 mock 서버를
  띄우고 시드 cycle을 ``TRASH_PI_SEEDED_CYCLE``로 노출했을 때만 검사(없으면 negative-only).

접속 주소 단일 원천은 SSH ``rp4b`` 별칭이다. 주소가 바뀌면 ``~/.ssh/config``의 rp4b와
(원하면) ``TRASH_PI_HOST`` 한 곳만 고치면 된다.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

PI_DIR = Path(__file__).resolve().parent.parent

# 라이브 Pi 타깃 — 기본은 현재 접속 주소. SSH rp4b 별칭과 일치시켜 단일 원천 유지.
PI_HOST = os.environ.get("TRASH_PI_HOST", "192.168.50.164")
PI_PORT = int(os.environ.get("TRASH_PI_PORT", "8080"))
# e2e_pi.sh up이 라이브 mock 서버에 시드한 cycle. 있으면 happy-path도 검사(없으면 negative-only).
SEEDED_CYCLE = os.environ.get("TRASH_PI_SEEDED_CYCLE")

# 최소 유효 JPEG(SOI + JFIF APP0 + EOI). mock 분류기는 바이트를 파싱하지 않으므로 내용 무관.
SEED_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
)
LOCAL_SEED_CYCLE = 424242  # Tier A 로컬 시드 cycle
MISSING_CYCLE = 314159  # 어느 타깃에도 시드되지 않는다고 가정 → 404 경로 검증용


# --- 공용 HTTP 헬퍼 ---------------------------------------------------------


def _reachable(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _get(url: str, timeout: float = 5.0):
    return urllib.request.urlopen(url, timeout=timeout)


def _post(url: str, body: bytes = b"", timeout: float = 30.0):
    return urllib.request.urlopen(
        urllib.request.Request(url, data=body, method="POST"), timeout=timeout
    )


def _raw_status_line(host: str, port: int, raw: bytes, timeout: float = 3.0) -> bytes:
    """urllib이 정규화하지 못하는 malformed framing을 raw 소켓으로 보내고 상태줄을 받는다."""
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall(raw)
        return sock.recv(256).split(b"\r\n", 1)[0]


# --- 타깃 공통 계약(base_url만 다름) ----------------------------------------


def _assert_photo_missing_404(base: str, cycle: int = MISSING_CYCLE) -> None:
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(f"{base}/photos/{cycle}.jpg")
    assert exc.value.code == 404


def _assert_path_traversal_404(base: str) -> None:
    # 디렉터리 리스팅·경로탈출·비숫자 cycle은 전부 404(photo_server 정규식 매칭 실패).
    for path in ("/etc/passwd", "/photos/abc.jpg", "/photos/../secret"):
        with pytest.raises(urllib.error.HTTPError) as exc:
            _get(base + path)
        assert exc.value.code == 404


def _assert_classify_missing_404(base: str, cycle: int = MISSING_CYCLE) -> None:
    # 사진이 없으면 분류기 호출 전에 404 — 라이브 Gemini라도 쿼터를 쓰지 않는다.
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(f"{base}/classify/{cycle}")
    assert exc.value.code == 404


def _assert_classify_shape(base: str, cycle: int) -> dict:
    with _post(f"{base}/classify/{cycle}") as resp:
        assert resp.status == 200
        body = json.loads(resp.read())
    assert body["category"] in {"pet", "can", "other"}  # 3분류 정규화 계약
    assert isinstance(body["description"], str)  # 재활용 팁
    assert 0.0 <= body["confidence"] <= 1.0
    return body


# ============================================================================
# Tier A — 로컬: 실제 엔트리포인트를 mock 모드로 기동(하드웨어/BLE/카메라/Gemini 불필요)
# ============================================================================


def _terminate(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    # start_new_session=True → 자체 프로세스그룹. 그룹째 정리(자식 오펀 방지).
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        proc.wait(timeout=5)


@pytest.fixture(scope="module")
def local_app(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    photo_dir = tmp_path_factory.mktemp("e2e-photos")
    (photo_dir / f"{LOCAL_SEED_CYCLE}.jpg").write_bytes(SEED_JPEG)
    log_path = photo_dir / "app.log"

    with socket.socket() as s:  # 빈 포트 확보(충돌 회피)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    env = {
        **os.environ,
        "TRASH_MOCK": "1",  # mock BLE/HW/camera → 실기기 의존 모듈 import 안 함
        "TRASH_PHOTO_DIR": str(photo_dir),  # 시드 사진을 서빙할 고정 디렉터리(TRASH_PHOTO_DIR)
        "TRASH_HTTP_PORT": str(port),
        "TRASH_PHOTO_RETENTION": "100000",  # 시드가 prune되지 않게
        "TRASH_HEARTBEAT": "3600",  # 조용히
        "TRASH_GEMINI_CREDENTIALS": "",  # 분류기 강제 Mock(결정적·네트워크/쿼터 불필요)
        "PYTHONPATH": str(PI_DIR / "src"),
        "PYTHONUNBUFFERED": "1",
    }
    with open(log_path, "wb") as log_f:
        proc = subprocess.Popen(
            [sys.executable, "-m", "trash_sorter"],
            cwd=str(PI_DIR),
            env=env,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 20.0
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    pytest.fail(
                        f"trash-sorter 엔트리포인트 조기 종료(code={proc.returncode}):\n"
                        f"{log_path.read_text(errors='replace')}"
                    )
                if _reachable("127.0.0.1", port, timeout=0.5):
                    break
                time.sleep(0.2)
            else:
                pytest.fail("trash-sorter HTTP 서버가 제한시간 내 기동되지 않음")
            yield f"http://127.0.0.1:{port}"
        finally:
            _terminate(proc)


def test_local_serves_seeded_photo(local_app: str) -> None:
    with _get(f"{local_app}/photos/{LOCAL_SEED_CYCLE}.jpg") as resp:
        assert resp.status == 200
        assert resp.headers["Content-Type"] == "image/jpeg"
        assert resp.read() == SEED_JPEG


def test_local_photo_missing_404(local_app: str) -> None:
    _assert_photo_missing_404(local_app)


def test_local_path_traversal_404(local_app: str) -> None:
    _assert_path_traversal_404(local_app)


def test_local_classify_seeded_mock(local_app: str) -> None:
    body = _assert_classify_shape(local_app, LOCAL_SEED_CYCLE)
    # iPad 보상 화면용 필드(eco_points·recyclable)까지 분류 계약 전체 확인.
    assert 0 <= body["eco_points"] <= 100
    assert isinstance(body["recyclable"], bool)


def test_local_classify_missing_404(local_app: str) -> None:
    _assert_classify_missing_404(local_app)


# ============================================================================
# Tier B — 라이브 Pi(TRASH_PI_HOST, 기본 192.168.50.164). 미도달 시 전 테스트 skip.
# ============================================================================


@pytest.fixture(scope="module")
def live_base() -> str:
    if not _reachable(PI_HOST, PI_PORT):
        pytest.skip(
            f"라이브 Pi HTTP 미도달({PI_HOST}:{PI_PORT}). "
            "기동: 저장소 루트에서 `pi/scripts/e2e_pi.sh up` "
            "(또는 다른 주소면 TRASH_PI_HOST=… 지정)."
        )
    return f"http://{PI_HOST}:{PI_PORT}"


def test_live_health_and_photo_missing_404(live_base: str) -> None:
    # fixture가 TCP 도달성 보장 + 미시드 cycle 404로 HTTP 라우팅 동작 확인(헬스체크).
    _assert_photo_missing_404(live_base)


def test_live_path_traversal_404(live_base: str) -> None:
    _assert_path_traversal_404(live_base)


def test_live_classify_missing_404(live_base: str) -> None:
    _assert_classify_missing_404(live_base)


def test_live_malformed_content_length_400(live_base: str) -> None:
    status = _raw_status_line(
        PI_HOST,
        PI_PORT,
        b"POST /classify/5 HTTP/1.1\r\nHost: x\r\n"
        b"Content-Length: abc\r\nConnection: close\r\n\r\n",
    )
    assert b"400" in status


def test_live_seeded_photo_and_classify(live_base: str) -> None:
    if not SEEDED_CYCLE:
        pytest.skip(
            "라이브 시드 cycle 없음(TRASH_PI_SEEDED_CYCLE 미설정). "
            "`pi/scripts/e2e_pi.sh up`이 시드 후 이 값을 안내한다."
        )
    cycle = int(SEEDED_CYCLE)
    with _get(f"{live_base}/photos/{cycle}.jpg") as resp:
        assert resp.status == 200
        assert resp.headers["Content-Type"] == "image/jpeg"
    _assert_classify_shape(live_base, cycle)
