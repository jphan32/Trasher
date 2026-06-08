"""사진 HTTP 서버 + 순환보관 테스트."""

from __future__ import annotations

import urllib.error
import urllib.request

import pytest

from trash_sorter.web import PhotoServer, PhotoStore, get_lan_ip


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
