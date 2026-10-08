"""Producción: la API vive en /api y la misma app sirve la web (un servicio, mismo origen)."""

import pytest
from fastapi.testclient import TestClient

from core.profile import service as profiles


@pytest.fixture
def site(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id=root></div>")
    (dist / "assets" / "app.js").write_text("console.log('hola')")
    (tmp_path / "secreto.txt").write_text("no")
    monkeypatch.setenv("API_PREFIX", "/api")
    monkeypatch.setenv("WEB_DIST", str(dist))
    monkeypatch.setenv("API_INPROCESS_WORKER", "0")
    monkeypatch.setenv("AUTH_DEV_SECRET", "x" * 40)
    monkeypatch.setenv("AUTH_DEV_LOGIN", "1")
    monkeypatch.setattr(profiles, "_ready", False)
    from api.main import create_app

    with TestClient(create_app()) as client:
        yield client


def test_api_under_prefix_and_web_everywhere_else(site):
    assert site.get("/api/health").json() == {"status": "ok"}
    assert site.get("/api/me").status_code == 401  # la API exige el token igual
    token = site.post("/api/dev/token", json={"name": "Ana"}).json()["token"]
    assert site.get("/api/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    for path in ("/", "/bandeja", "/postulaciones/12"):
        r = site.get(path)
        assert r.status_code == 200 and "id=root" in r.text and r.headers["cache-control"] == "no-cache", path
    asset = site.get("/assets/app.js")
    assert asset.text == "console.log('hola')" and "immutable" in asset.headers["cache-control"]
    page = site.get("/")
    assert page.headers["x-frame-options"] == "DENY" and "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert site.get("/a%00b").status_code == 200
    assert site.get("/api/docs").status_code == 200


def test_unknown_api_paths_and_traversal_do_not_leak(site):
    r = site.get("/api/no-existe")
    assert r.status_code == 404 and r.json() == {"detail": "No encontrado"}
    assert site.get("/me").headers["content-type"].startswith("text/html")  # sin prefijo no es la API
    for path in ("/../secreto.txt", "/%2e%2e/secreto.txt", "/assets/../../secreto.txt"):
        assert site.get(path).text != "no", path


def test_serving_the_web_requires_a_prefix(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("x")
    (tmp_path / "assets").mkdir()
    monkeypatch.setenv("WEB_DIST", str(tmp_path))
    monkeypatch.delenv("API_PREFIX", raising=False)
    from api.main import create_app

    with pytest.raises(RuntimeError, match="API_PREFIX"):
        create_app()
