"""HTTP API surface tests."""

import os
import tempfile

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client(monkeypatch):
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("CONTINUUM_HOME", tmp)
    monkeypatch.setenv("CONTINUUM_BACKEND", "local")
    import continuum.surfaces.api as api

    api._engines.clear()  # reset per-user engine cache for isolation
    return TestClient(api.app)


def test_health(client):
    assert client.get("/health").json()["ok"] is True


def test_checkpoint_resume_roundtrip(client):
    text = (
        "User: build auth, low ops.\n\n"
        "Assistant: use JWT + PKCE, stateless.\n\n"
        "User: let's not use Redis because of the lock race. next: refresh endpoint."
    )
    r = client.post("/checkpoint", json={"project": "auth", "text": text})
    assert r.status_code == 200 and r.json()["checkpoint_id"].startswith("cp-")

    r = client.post("/resume", json={"project": "auth", "intent": "refresh endpoint"})
    pkg = r.json()["resume_package"]
    assert "RESUME PACKAGE" in pkg and "Redis" in pkg

    assert client.get("/status/auth").json()["has_state"] is True


def test_empty_checkpoint_rejected(client):
    assert client.post("/checkpoint", json={"project": "x", "text": "  "}).status_code == 400


def test_projects_and_forget(client):
    client.post("/checkpoint", json={"project": "a", "text": "use X because Y. next: ship."})
    assert "a" in client.get("/projects").json()["projects"]
    client.delete("/projects/a")
    assert "a" not in client.get("/projects").json()["projects"]


def test_token_auth(monkeypatch, client):
    monkeypatch.setenv("CONTINUUM_TOKEN", "secret")
    assert client.get("/status/x").status_code == 401
    ok = client.get("/status/x", headers={"Authorization": "Bearer secret"})
    assert ok.status_code == 200
    assert client.get("/health").status_code == 200  # health stays open
