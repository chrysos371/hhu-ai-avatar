import threading
import urllib.error
import urllib.request

import pytest

from avatar.web import create_server


@pytest.fixture
def static_server(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        '<!doctype html><html><body>Mission Control<script type="module" src="/assets/app-123.js"></script></body></html>'
    )
    (dist / "assets/app-123.js").write_text('console.log("local")')
    (tmp_path / "secret.txt").write_text("SECRET")
    server = create_server(str(tmp_path / "test.db"), port=0, frontend_dir=dist)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def get(path):
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{server.server_port}" + path
            ) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as r:
            return r.code, r.headers, r.read()

    yield get, dist
    server.shutdown()
    thread.join()
    server.server_close()


def test_server_serves_spa_and_hashed_assets(static_server):
    get, _ = static_server
    status, headers, body = get("/")
    assert status == 200 and b"Mission Control" in body
    assert "script-src 'self'" in headers["Content-Security-Policy"]
    assert headers["Cache-Control"] == "no-store"
    assert get("/assets/app-123.js")[1]["Content-Type"].startswith("text/javascript")
    assert get("/persona")[2] == body


def test_spa_fallback_does_not_shadow_api(static_server):
    get, _ = static_server
    assert get("/api/nope")[0] == 403
    assert get("/api")[0] == 404


@pytest.mark.parametrize(
    "path",
    [
        "/assets/../secret.txt",
        "/assets/%2e%2e/%2e%2e/secret.txt",
        "/assets/%252e%252e/secret.txt",
        "/.env",
    ],
)
def test_static_path_traversal_is_rejected(static_server, path):
    get, _ = static_server
    status, _, body = get(path)
    assert status == 404 and b"SECRET" not in body


def test_missing_dist_returns_build_instructions(static_server):
    get, dist = static_server
    (dist / "index.html").unlink()
    assert b"npm" in get("/")[2] and b"build" in get("/")[2]


def test_corrupt_dist_and_external_symlink_do_not_leak(static_server):
    get, dist = static_server
    (dist / "assets/app-123.js").unlink()
    assert b"build" in get("/")[2]
    (dist / "assets/leak.js").symlink_to(dist.parent / "secret.txt")
    assert get("/assets/leak.js")[0] == 404
