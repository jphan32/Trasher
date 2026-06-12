"""사진 HTTP 서버 + 순환보관 테스트."""

from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request

import pytest

from trash_sorter.classify import MockClassifier
from trash_sorter.web import PhotoServer, PhotoStore, get_lan_ip


def _post(url: str):
    return urllib.request.urlopen(
        urllib.request.Request(url, data=b"", method="POST"), timeout=2
    )


def _put(url: str, payload: dict):
    data = json.dumps(payload).encode()
    return urllib.request.urlopen(
        urllib.request.Request(url, data=data, method="PUT"), timeout=2
    )


def test_store_path_and_url(tmp_path) -> None:
    store = PhotoStore(tmp_path / "photos", retention=3)
    assert store.path_for(42).name == "42.jpg"
    assert store.url_path(42) == "/photos/42.jpg"


def test_retention_prunes_oldest(tmp_path) -> None:
    store = PhotoStore(tmp_path / "photos", retention=2)
    for cycle in range(5):
        p = store.path_for(cycle)
        p.write_bytes(b"x")
        # mtime을 단조 증가시켜 순서를 결정적으로
        import os
        os.utime(p, (cycle, cycle))
    store.prune()
    remaining = sorted(int(p.stem) for p in (tmp_path / "photos").glob("*.jpg"))
    assert remaining == [3, 4]  # 최근 2장만


def test_prune_tolerates_missing_file(tmp_path) -> None:
    # glob~stat 사이 파일이 사라져도(TOCTOU) prune이 예외 없이 진행되어야 메인 루프가 보호된다.
    photos = tmp_path / "photos"
    store = PhotoStore(photos, retention=1)
    (photos / "1.jpg").write_bytes(b"x")
    # stat 시 FileNotFoundError를 던지는 깨진 심볼릭 링크(glob에는 잡히지만 stat은 실패).
    (photos / "2.jpg").symlink_to(photos / "does-not-exist.jpg")
    store.prune()  # raise하지 않아야 함


def test_classify_accepts_request_with_body(tmp_path) -> None:
    # m5: 본문이 있는 POST도 본문을 소비해 정상 200 응답(연결 desync 방지).
    store = PhotoStore(tmp_path / "photos")
    store.path_for(4).write_bytes(b"\xff\xd8jpeg\xff\xd9")
    server = PhotoServer(store, port=0, host="127.0.0.1", classifier=MockClassifier())
    server.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.port}/classify/4", data=b"ignored-body", method="POST"
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            assert resp.status == 200
            assert json.loads(resp.read())["category"] in {"pet", "can", "other"}
    finally:
        server.stop()


def test_classify_rejects_malformed_content_length(tmp_path) -> None:
    # m5: 잘못된 Content-Length는 핸들러를 죽이지 않고 400으로 정리(워커 보호).
    # urllib이 헤더를 정규화하므로 raw 소켓으로 malformed framing을 직접 보낸다.
    store = PhotoStore(tmp_path / "photos")
    store.path_for(5).write_bytes(b"\xff\xd8")
    server = PhotoServer(store, port=0, host="127.0.0.1", classifier=MockClassifier())
    server.start()
    try:
        with socket.create_connection(("127.0.0.1", server.port), timeout=2) as sock:
            sock.sendall(
                b"POST /classify/5 HTTP/1.1\r\nHost: x\r\n"
                b"Content-Length: abc\r\nConnection: close\r\n\r\n"
            )
            status_line = sock.recv(256).split(b"\r\n", 1)[0]
        assert b"400" in status_line
    finally:
        server.stop()


def test_server_serves_existing_photo(tmp_path) -> None:
    store = PhotoStore(tmp_path / "photos")
    store.path_for(7).write_bytes(b"\xff\xd8JPEGDATA\xff\xd9")
    server = PhotoServer(store, port=0, host="127.0.0.1")
    server.start()
    try:
        url = f"http://127.0.0.1:{server.port}/photos/7.jpg"
        with urllib.request.urlopen(url, timeout=2) as resp:
            assert resp.status == 200
            assert resp.headers["Content-Type"] == "image/jpeg"
            assert resp.read() == b"\xff\xd8JPEGDATA\xff\xd9"
    finally:
        server.stop()


def test_server_404_for_missing_and_bad_path(tmp_path) -> None:
    store = PhotoStore(tmp_path / "photos")
    server = PhotoServer(store, port=0, host="127.0.0.1")
    server.start()
    try:
        base = f"http://127.0.0.1:{server.port}"
        for path in ("/photos/999.jpg", "/etc/passwd", "/photos/abc.jpg"):
            with pytest.raises(urllib.error.HTTPError) as exc:
                urllib.request.urlopen(base + path, timeout=2)
            assert exc.value.code == 404
    finally:
        server.stop()


def test_get_lan_ip_returns_ipv4() -> None:
    ip = get_lan_ip()
    parts = ip.split(".")
    assert len(parts) == 4 and all(p.isdigit() for p in parts)


def test_classify_endpoint_returns_result(tmp_path) -> None:
    store = PhotoStore(tmp_path / "photos")
    store.path_for(3).write_bytes(b"\xff\xd8jpeg\xff\xd9")
    server = PhotoServer(store, port=0, host="127.0.0.1", classifier=MockClassifier())
    server.start()
    try:
        with _post(f"http://127.0.0.1:{server.port}/classify/3") as resp:
            assert resp.status == 200
            body = json.loads(resp.read())
        assert body["category"] in {"pet", "can", "other"}
        assert body["description"]  # 재활용 팁
        assert 0.0 <= body["confidence"] <= 1.0
        assert 0 <= body["eco_points"] <= 100  # 탄소절감 에코포인트
        assert isinstance(body["recyclable"], bool)
    finally:
        server.stop()


def test_classify_missing_photo_404(tmp_path) -> None:
    store = PhotoStore(tmp_path / "photos")
    server = PhotoServer(store, port=0, host="127.0.0.1", classifier=MockClassifier())
    server.start()
    try:
        with pytest.raises(urllib.error.HTTPError) as exc:
            _post(f"http://127.0.0.1:{server.port}/classify/999")
        assert exc.value.code == 404
    finally:
        server.stop()


def test_classify_without_classifier_503(tmp_path) -> None:
    store = PhotoStore(tmp_path / "photos")
    store.path_for(1).write_bytes(b"\xff\xd8")
    server = PhotoServer(store, port=0, host="127.0.0.1")  # classifier=None
    server.start()
    try:
        with pytest.raises(urllib.error.HTTPError) as exc:
            _post(f"http://127.0.0.1:{server.port}/classify/1")
        assert exc.value.code == 503
    finally:
        server.stop()


# --- 런타임 설정 엔드포인트(docs/protocol.md §8) ----------------------------
def _config_server(tmp_path):
    from trash_sorter.config import Settings
    from trash_sorter.config_manager import ConfigManager

    settings = Settings()
    cm = ConfigManager(settings)
    store = PhotoStore(tmp_path / "photos")
    server = PhotoServer(store, port=0, host="127.0.0.1", config_manager=cm)
    return server, settings


def test_get_config_returns_schema(tmp_path) -> None:
    server, _ = _config_server(tmp_path)
    server.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.port}/config", timeout=2) as resp:
            assert resp.status == 200
            body = json.loads(resp.read())
        belt = next(f for f in body["fields"] if f["key"] == "belt_run_seconds")
        assert belt["value"] == 3.0 and belt["max"] == 15.0
    finally:
        server.stop()


def test_put_config_applies_clamps_and_persists_to_settings(tmp_path) -> None:
    server, settings = _config_server(tmp_path)
    server.start()
    try:
        base = f"http://127.0.0.1:{server.port}/config"
        with _put(base, {"belt_run_seconds": 999}) as resp:  # over max → clamp 15.0
            assert resp.status == 200
            body = json.loads(resp.read())
        assert body["ok"] is True and body["applied"]["belt_run_seconds"] == 15.0
        assert body["persisted"] is True  # 영속 경로 미설정 → 실패 아님
        assert settings.belt.run_seconds == 15.0  # 공유 Settings에 즉시 반영(HOT)
        # GET이 변경을 반영
        with urllib.request.urlopen(base, timeout=2) as resp:
            fields = json.loads(resp.read())["fields"]
        belt = next(f for f in fields if f["key"] == "belt_run_seconds")
        assert belt["value"] == 15.0
    finally:
        server.stop()


def test_put_config_unknown_field_400(tmp_path) -> None:
    server, settings = _config_server(tmp_path)
    server.start()
    try:
        with pytest.raises(urllib.error.HTTPError) as exc:
            _put(f"http://127.0.0.1:{server.port}/config", {"bogus": 1})
        assert exc.value.code == 400
        assert settings.belt.run_seconds == 3.0  # 거부 시 변경 없음
    finally:
        server.stop()


def test_config_endpoints_503_without_manager(tmp_path) -> None:
    store = PhotoStore(tmp_path / "photos")
    server = PhotoServer(store, port=0, host="127.0.0.1")  # config_manager=None
    server.start()
    try:
        base = f"http://127.0.0.1:{server.port}/config"
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(base, timeout=2)
        assert exc.value.code == 503
        with pytest.raises(urllib.error.HTTPError) as exc:
            _put(base, {"belt_run_seconds": 2.0})
        assert exc.value.code == 503
    finally:
        server.stop()
