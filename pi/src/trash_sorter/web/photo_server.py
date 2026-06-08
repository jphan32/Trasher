"""로컬 WiFi 사진 HTTP 서버. docs/protocol.md §"사진 채널", §3.3.

- ``PhotoStore``: cycle별 사진 경로 + 순환 보관(최근 N장).
- ``PhotoServer``: ``GET /photos/{cycle}.jpg``만 서빙(디렉터리 리스팅·경로탈출 차단).
- ``get_lan_ip``: DeviceInfo로 광고할 LAN IP 자동 감지.
"""

from __future__ import annotations

import re
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_PHOTO_RE = re.compile(r"/photos/(\d+)\.jpg")


def get_lan_ip() -> str:
    """기본 라우트로 나가는 인터페이스의 IP. 실제 패킷은 보내지 않는다."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return str(s.getsockname()[0])
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class PhotoStore:
    def __init__(self, directory: str | Path, retention: int = 20) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._retention = retention

    def path_for(self, cycle: int) -> Path:
        return self._dir / f"{cycle}.jpg"

    @staticmethod
    def url_path(cycle: int) -> str:
        return f"/photos/{cycle}.jpg"

    def prune(self) -> None:
        """최근 retention장만 남기고 오래된 사진 삭제(mtime 기준)."""
        files = sorted(self._dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime)
        for p in files[: max(0, len(files) - self._retention)]:
            p.unlink(missing_ok=True)


def _make_handler(store: PhotoStore) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            m = _PHOTO_RE.fullmatch(self.path)
            if not m:
                self.send_error(404)
                return
            path = store.path_for(int(m.group(1)))
            try:
                data = path.read_bytes()
            except OSError:
                # 파일 없음 / prune과의 경쟁(TOCTOU) → 404
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                # iPad가 전송 도중 취소(타임아웃/백그라운드) — 조용히 종료, 트레이스백 없음
                pass

        def log_message(self, *args: object) -> None:  # 조용히
            pass

    return Handler


class PhotoServer:
    def __init__(self, store: PhotoStore, port: int = 8080, host: str = "0.0.0.0") -> None:
        self._store = store
        self._httpd = ThreadingHTTPServer((host, port), _make_handler(store))
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return int(self._httpd.server_address[1])

    def start(self) -> None:
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        if self._thread:
            self._thread.join(timeout=2)
