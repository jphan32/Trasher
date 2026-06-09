"""로컬 WiFi 사진 HTTP 서버 + 분류 엔드포인트. docs/protocol.md §"사진 채널", §3.3, §4.4.

- ``PhotoStore``: cycle별 사진 경로 + 순환 보관(최근 N장).
- ``PhotoServer``:
  - ``GET /photos/{cycle}.jpg`` — 사진 서빙(디렉터리 리스팅·경로탈출 차단).
  - ``POST /classify/{cycle}`` — 로컬 사진을 읽어 분류기(Gemini/Mock) 호출.
    응답: {category, description, confidence}. iPad는 이미지 대신 cycle ID만 보낸다(재업로드 없음).
- ``get_lan_ip``: DeviceInfo로 광고할 LAN IP 자동 감지.
"""

from __future__ import annotations

import json
import re
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..classify import Classifier

_PHOTO_RE = re.compile(r"/photos/(\d+)\.jpg")
_CLASSIFY_RE = re.compile(r"/classify/(\d+)")
_MAX_BODY_BYTES = 1 << 20  # /classify 본문 상한(1MB) — 과대 framing 방어


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
        """최근 retention장만 남기고 오래된 사진 삭제(mtime 기준).

        glob~stat 사이 파일이 사라지면(TOCTOU) OSError가 날 수 있다. prune은 베스트-에포트라
        실패가 오케스트레이터 메인 루프(tick)를 죽이지 않도록 통째로 가드한다.
        """
        try:
            files = sorted(self._dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime)
            for p in files[: max(0, len(files) - self._retention)]:
                p.unlink(missing_ok=True)
        except OSError:
            pass  # 정리 실패는 무시(다음 사이클에 재시도)


def _make_handler(
    store: PhotoStore, classifier: Classifier | None
) -> type[BaseHTTPRequestHandler]:
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
            self._write(data)

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            # POST /classify/{cycle} — 로컬 사진을 읽어 분류(이미지 재업로드 없음)
            # 요청 본문을 끝까지 소비해야 keep-alive 연결이 다음 요청과 desync되지 않는다
            # (iPad는 빈 본문을 보내 보통 no-op). 잘못된 framing은 400/413으로 정리.
            raw_len = self.headers.get("Content-Length")
            try:
                length = int(raw_len) if raw_len is not None else 0
            except ValueError:
                self.send_error(400)
                return
            if length < 0:
                self.send_error(400)
                return
            if length > _MAX_BODY_BYTES:
                self.send_error(413)
                return
            if length > 0:
                self.rfile.read(length)
            m = _CLASSIFY_RE.fullmatch(self.path)
            if not m:
                self.send_error(404)
                return
            if classifier is None:
                self._json(503, {"error": "classifier not configured"})
                return
            path = store.path_for(int(m.group(1)))
            try:
                data = path.read_bytes()
            except OSError:
                self.send_error(404)
                return
            try:
                result = classifier.classify(data)
            except Exception as e:  # noqa: BLE001 - 분류 실패는 502로
                self._json(502, {"error": str(e)[:300]})
                return
            self._json(200, result.to_dict())

        def _json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self._write(body)

        def _write(self, data: bytes) -> None:
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                # 클라이언트가 전송 도중 취소 — 조용히 종료, 트레이스백 없음
                pass

        def log_message(self, *args: object) -> None:  # 조용히
            pass

    return Handler


class PhotoServer:
    def __init__(
        self, store: PhotoStore, port: int = 8080, host: str = "0.0.0.0",
        classifier: Classifier | None = None,
    ) -> None:
        self._store = store
        self._httpd = ThreadingHTTPServer((host, port), _make_handler(store, classifier))
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
