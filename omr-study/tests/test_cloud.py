"""Exercise provider HTTP contracts with a private in-memory storage service."""

import base64
import json
from urllib.parse import unquote
import httpx
import pytest
from fastapi.testclient import TestClient
from tests.test_web import register, payload
from backend.main import app
from backend import storage
from backend.database import SessionLocal, StoredFile, DATA
from omr.io import ROOT


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://storage.test")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "server-only-secret")
    objects = {}
    storage.require_private_bucket.cache_clear()

    def serve(request):
        path = unquote(request.url.path).removeprefix("/storage/v1")
        assert request.headers["apikey"] == "server-only-secret"
        if path == "/bucket/omr-private":
            return httpx.Response(200, json={"public": False})
        if path.startswith("/object/upload/sign/"):
            return httpx.Response(200, json={"url": path + "?token=upload-token"})
        if path.startswith("/object/sign/"):
            return httpx.Response(200, json={"signedURL": path + "?token=read-token"})
        if path.startswith("/object/authenticated/"):
            key = path.removeprefix("/object/authenticated/omr-private/")
            return (
                httpx.Response(200, content=objects[key])
                if key in objects
                else httpx.Response(404)
            )
        if request.method == "DELETE":
            for key in json.loads(request.content)["prefixes"]:
                objects.pop(key, None)
            return httpx.Response(200, json=[])
        if request.method == "POST" and path.startswith("/object/omr-private/"):
            key = path.removeprefix("/object/omr-private/")
            assert request.headers["x-upsert"] == "false"
            objects[key] = request.content
            return httpx.Response(200, json={"Key": key})
        raise AssertionError((request.method, path))

    with httpx.Client(transport=httpx.MockTransport(serve)) as client:
        monkeypatch.setattr(storage.httpx, "request", client.request)
        monkeypatch.setattr(storage.httpx, "stream", client.stream)
        yield objects


def upload(client, objects, kind="original"):
    r = client.post(
        "/api/uploads/sign", json={"filename": "math.png", "size": 100, "kind": kind}
    )
    assert r.status_code == 200, r.text
    ticket = r.json()
    assert "server-only-secret" not in r.text
    assert "https://storage.test/storage/v1/object/upload/sign/" in ticket["upload_url"]
    with SessionLocal() as db:
        key = db.get(StoredFile, ticket["file_id"]).path.removeprefix("supabase:")
    objects[key] = (ROOT / "assets/template_math.png").read_bytes()
    return ticket["file_id"]


def test_private_upload_analysis_backup_and_delete(provider):
    a, b = TestClient(app), TestClient(app)
    register(a, "cloud-owner")
    register(b, "cloud-other")
    assert a.get("/api/config").json()["direct_upload"]
    file_id = upload(a, provider)
    assert a.get("/api/files/" + file_id).status_code == 404
    assert b.post("/api/uploads/complete", json={"file_id": file_id}).status_code == 404
    assert (
        a.post(
            "/api/omr/analyze-page", json={"file_id": file_id, "page": 1}
        ).status_code
        == 422
    )
    assert (
        a.post("/api/uploads/complete", json={"file_id": file_id}).json()["pages"] == 1
    )
    assert (
        b.post(
            "/api/omr/analyze-page", json={"file_id": file_id, "page": 1}
        ).status_code
        == 404
    )
    r = a.post("/api/omr/analyze-page", json={"file_id": file_id, "page": 1})
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["pages"][0]["subject"] == "math"
    crop = result["pages"][0]["answers"]["16"]["crop_file_id"]
    assert crop
    assert not list(DATA.glob("download-*")), "temporary analysis files must be removed"
    assert b.get("/api/files/" + crop).status_code == 404
    r = a.get("/api/files/" + crop, follow_redirects=False)
    assert r.status_code == 307 and "read-token" in r.headers["location"]
    data = payload()
    data["file_ids"] = result["file_ids"]
    data["subjects"][0]["questions"][15]["crop_file_id"] = crop
    exam = a.post("/api/exams", json=data).json()
    manifest = a.get("/api/export?manifest=true").json()
    entry = next(f for f in manifest["files"] if f["id"] == file_id)
    assert "data" not in entry and entry["url"] == "/api/files/" + file_id
    full = a.get("/api/export").json()
    original = next(f for f in full["files"] if f["id"] == file_id)
    assert (
        base64.b64decode(original["data"])
        == (ROOT / "assets/template_math.png").read_bytes()
    )
    assert a.delete("/api/exams/" + exam["id"]).status_code == 200
    assert not provider


def test_cloud_restore_ownership_and_duplicate_check(provider):
    a, b = TestClient(app), TestClient(app)
    register(a, "cloud-restore")
    register(b, "cloud-restore-other")
    file_id = upload(a, provider, "backup-asset")
    assert a.post("/api/uploads/complete", json={"file_id": file_id}).status_code == 200
    exam = {**payload(), "id": "old-backup-exam", "file_ids": ["old-file"]}
    backup = {
        "version": 1,
        "exams": [exam],
        "files": [{"id": "old-file", "stored_file_id": file_id, "kind": "original"}],
    }
    assert b.post("/api/import", json=backup).status_code == 422
    assert a.post("/api/import", json=backup).json()["added"] == 1
    assert a.post("/api/import", json=backup).json()["skipped"] == 1
    assert a.post("/api/import/check", json={"original_id": exam["id"]}).json()[
        "exists"
    ]
    assert not b.post("/api/import/check", json={"original_id": exam["id"]}).json()[
        "exists"
    ]


def test_cloud_limits_and_pending_file_cannot_attach(provider):
    a = TestClient(app)
    register(a, "cloud-limits")
    assert (
        a.post(
            "/api/uploads/sign", json={"filename": "bad.html", "size": 1}
        ).status_code
        == 422
    )
    assert (
        a.post(
            "/api/uploads/sign", json={"filename": "big.pdf", "size": storage.LIMIT + 1}
        ).status_code
        == 422
    )
    file_id = upload(a, provider)
    data = payload()
    data["file_ids"] = [file_id]
    assert a.post("/api/exams", json=data).status_code == 422
    with SessionLocal() as db:
        key = db.get(StoredFile, file_id).path.removeprefix("supabase:")
    provider[key] = b"invalid-image"
    assert a.post("/api/uploads/complete", json={"file_id": file_id}).status_code == 422
    assert a.get("/api/files/" + file_id).status_code == 404
