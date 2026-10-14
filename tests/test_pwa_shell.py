"""Regressão de rotas e proteção do primeiro estágio PWA."""
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.pwa import monter_routes


def _client():
    app = FastAPI()
    monter_routes(app)
    return TestClient(app)


def test_home_is_static_portuguese_and_no_store():
    with _client() as client:
        response = client.get("/")
    assert response.status_code == 200
    assert 'lang="pt-BR"' in response.text
    assert "Jarvis" in response.text
    assert response.headers["cache-control"] == "no-store, private"
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-robots-tag"] == "noindex, nofollow"


def test_manifest_and_sw():
    with _client() as client:
        manifest = client.get("/manifest.webmanifest")
        sw = client.get("/sw.js")
    assert manifest.status_code == 200
    assert json.loads(manifest.text)["start_url"] == "/"
    assert sw.status_code == 200
    assert sw.headers["service-worker-allowed"] == "/"


def test_asset_whitelist_prevents_unrelated_file_access():
    with _client() as client:
        assert client.get("/pwa/app.js").status_code == 200
        assert client.get("/pwa/icon.svg").status_code == 200
        assert client.get("/pwa/config.yaml").status_code == 404
        assert client.get("/pwa/core/serveur.py").status_code == 404
