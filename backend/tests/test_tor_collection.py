"""Exercices hors réseau : jamais de connexion à un service Onion."""
import asyncio
import base64
import hashlib
import uuid
from dataclasses import dataclass

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.collector.extract import extract_html
from app.collector.runner import NotAuthorizedError, collect_one
from app.collector.transport import CollectError, Fetched, MAX_BODY, fetch_onion_root
from app.models import AuditLog, CrawlJob, DiscoveredOnion, OnionSource, SourceObservation

API_HEADERS = {"X-API-Key": "local-test-only-api-key-strong-and-unique"}
REASON = {"reason": "Demande expresse du responsable de veille"}


def onion(seed: int) -> str:
    key = bytes((seed + i) % 256 for i in range(32))
    checksum = hashlib.sha3_256(b".onion checksum" + key + b"\x03").digest()[:2]
    return "http://" + base64.b32encode(key + checksum + b"\x03").decode().lower().rstrip("=") + ".onion/"


def create(client: TestClient, url: str) -> str:
    response = client.post("/api/v1/sources", headers=API_HEADERS, json={
        "url": url, "name": "Source autorisée", "authorization_confirmed": True,
        "authorization_note": "Validation écrite de consultation publique",
    })
    assert response.status_code == 201, response.text
    return response.json()["id"]


def enabled(client: TestClient, valid_onion_url: str) -> str:
    source_id = create(client, valid_onion_url)
    response = client.post(f"/api/v1/sources/{source_id}/collection/enable", headers=API_HEADERS, json=REASON)
    assert response.status_code == 200, response.text
    assert response.json()["collection_enabled"] is True
    return source_id


def test_collection_requires_key(client: TestClient):
    assert client.get("/api/v1/collection/jobs").status_code == 401
    assert client.get("/api/v1/collection/observations").status_code == 401
    assert client.get("/api/v1/collection/discoveries").status_code == 401


def test_collection_initially_disabled(client: TestClient, valid_onion_url: str):
    sid = create(client, valid_onion_url)
    response = client.get(f"/api/v1/sources/{sid}", headers=API_HEADERS)
    assert response.json()["collection_enabled"] is False


def test_explicit_enable_disable_audited(client: TestClient, valid_onion_url: str):
    sid = enabled(client, valid_onion_url)
    response = client.post(f"/api/v1/sources/{sid}/collection/disable", headers=API_HEADERS, json=REASON)
    assert response.status_code == 200
    assert response.json()["collection_enabled"] is False
    history = client.get(f"/api/v1/sources/{sid}/history", headers=API_HEADERS).json()
    assert {x["action"] for x in history["items"]} >= {"collection.enable", "collection.disable"}


def test_revoke_blocks_reenable(client: TestClient, valid_onion_url: str):
    sid = enabled(client, valid_onion_url)
    revoked = client.post(f"/api/v1/sources/{sid}/revoke", headers=API_HEADERS, json=REASON)
    assert revoked.json()["collection_enabled"] is False
    attempted = client.post(f"/api/v1/sources/{sid}/collection/enable", headers=API_HEADERS, json=REASON)
    assert attempted.status_code == 409


def test_activation_not_approval(client: TestClient, valid_onion_url: str):
    sid = enabled(client, valid_onion_url)
    disabled = client.post(f"/api/v1/sources/{sid}/deactivate", headers=API_HEADERS, json=REASON)
    assert not disabled.json()["collection_enabled"]
    assert client.post(f"/api/v1/sources/{sid}/collection/enable", headers=API_HEADERS, json=REASON).status_code == 409


def test_invalid_reason_rejected(client: TestClient, valid_onion_url: str):
    sid = create(client, valid_onion_url)
    response = client.post(f"/api/v1/sources/{sid}/collection/enable", headers=API_HEADERS, json={"reason":"ok"})
    assert response.status_code == 422


def test_extract_scripts_not_in_digest_and_candidates_nonvisited(valid_onion_url: str):
    other = onion(99)
    raw = f'''<html><head><title>  Public   page </title><meta name="description" content="Info"/></head>
    <body><script>do_bad_thing()</script><nav>skip</nav><main>Alpha Beta</main>
    <a href="{other}some/path">Other</a><a href="{other}different/path">Again</a>
    <a href="http://127.0.0.1/private">Local</a></body></html>'''
    data = extract_html(raw.encode(), "utf-8", content_type="text/html", page_url=valid_onion_url)
    assert data.title == "Public page"
    assert data.description == "Info"
    assert data.onion_roots == (other,)
    assert data.text_length > 0
    clean = extract_html(raw.replace("do_bad_thing()", "another_script()").encode(), "utf-8", content_type="text/html", page_url=valid_onion_url)
    assert clean.text_sha256 == data.text_sha256


def test_extract_plaintext_and_invalid_encoding(valid_onion_url: str):
    data = extract_html(b"hello text", "nonexistent-encoding", content_type="text/plain", page_url=valid_onion_url)
    assert data.text_length == 10 and not data.onion_roots


class FakeStream:
    def __init__(self, *, status=200, kind="text/html", payload=b"<title>OK</title>", length=None):
        self.status_code = status
        self.headers = {"content-type": kind}
        if length is not None:
            self.headers["content-length"] = str(length)
        self.payload = payload
        self.encoding = "utf-8"
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        return False
    async def aiter_raw(self, chunk_size=8192):
        for n in range(0, len(self.payload), chunk_size):
            yield self.payload[n:n+chunk_size]


class FakeClient:
    def __init__(self, stream, **kwargs):
        self.opts = kwargs
        self.resp = stream
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        return False
    def stream(self, method, url):
        assert method == "GET" and url.endswith(".onion/")
        return self.resp


@pytest.mark.parametrize("status,kind,length,code", [
    (301,"text/html",None,"REDIRECT_BLOCKED"),
    (404,"text/html",None,"HTTP_NOT_OK"),
    (200,"application/octet-stream",None,"MIME_BLOCKED"),
    (200,"text/html",MAX_BODY+1,"BODY_TOO_LARGE"),
])
def test_transport_blocks_unsafe_responses(monkeypatch, valid_onion_url, status, kind, length, code):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **opts: FakeClient(FakeStream(status=status, kind=kind, length=length), **opts))
    with pytest.raises(CollectError, match=code):
        asyncio.run(fetch_onion_root(valid_onion_url))


def test_transport_rejects_non_onion_and_no_proxy(valid_onion_url):
    with pytest.raises(ValueError):
        asyncio.run(fetch_onion_root("http://127.0.0.1/"))
    with pytest.raises(CollectError, match="PROXY_REQUIRED"):
        asyncio.run(fetch_onion_root(valid_onion_url, proxy="http://127.0.0.1:8000"))


def test_transport_caps_stream(monkeypatch, valid_onion_url):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **opts: FakeClient(FakeStream(payload=b"z"*(MAX_BODY+1)), **opts))
    with pytest.raises(CollectError, match="BODY_TOO_LARGE"):
        asyncio.run(fetch_onion_root(valid_onion_url))


def test_transport_pins_proxy_and_no_redirect(monkeypatch, valid_onion_url):
    seen = {}
    def factory(**opts):
        seen.update(opts)
        return FakeClient(FakeStream(), **opts)
    monkeypatch.setattr(httpx, "AsyncClient", factory)
    got = asyncio.run(fetch_onion_root(valid_onion_url))
    assert got.body == b"<title>OK</title>"
    assert seen["proxy"] == "socks5://tor:9050"
    assert seen["follow_redirects"] is False
    assert seen["trust_env"] is False


def test_runner_refuses_unenabled(client, valid_onion_url, db_session_factory):
    sid = create(client, valid_onion_url)
    called = []
    async def fetcher(url):
        called.append(url)
        return Fetched(200, "text/html", "utf-8", b"ok")
    with pytest.raises(NotAuthorizedError):
        asyncio.run(collect_one(uuid.UUID(sid), db_session_factory, fetcher=fetcher))
    assert not called


def test_runner_single_fetch_persists_metadata_only(client, valid_onion_url, db_session_factory):
    sid = enabled(client, valid_onion_url)
    target = onion(40)
    fetched = []
    async def fetcher(url):
        fetched.append(url)
        return Fetched(200, "text/html", "utf-8", f'<title>Example</title><main>Public claim</main><a href="{target}">link</a>'.encode())
    jid, state = asyncio.run(collect_one(uuid.UUID(sid), db_session_factory, fetcher=fetcher))
    assert state == "COMPLETED" and fetched == [valid_onion_url]
    with db_session_factory() as db:
        obs = db.scalar(select(SourceObservation).where(SourceObservation.job_id == jid))
        assert obs.title == "Example" and len(obs.text_sha256) == 64
        assert not hasattr(obs, "body")
        assert db.scalar(select(func.count()).select_from(DiscoveredOnion)) == 1
        assert db.scalar(select(DiscoveredOnion)).status == "PENDING"
        assert db.get(CrawlJob, jid).status == "COMPLETED"
    assert client.get("/api/v1/collection/jobs", headers=API_HEADERS).json()["total"] == 1
    assert client.get("/api/v1/collection/observations", headers=API_HEADERS).json()["total"] == 1
    assert client.get("/api/v1/collection/discoveries", headers=API_HEADERS).json()["total"] == 1


def test_runner_failure_metadata_only(client, valid_onion_url, db_session_factory):
    sid = enabled(client, valid_onion_url)
    async def fetcher(_url):
        raise CollectError("MIME_BLOCKED")
    jid, status = asyncio.run(collect_one(uuid.UUID(sid), db_session_factory, fetcher=fetcher))
    assert status == "FAILED"
    with db_session_factory() as db:
        job = db.get(CrawlJob, jid)
        assert job.error_code == "MIME_BLOCKED"
        assert db.scalar(select(func.count()).select_from(SourceObservation)) == 0


def test_revocation_during_fetch_discard_content(client, valid_onion_url, db_session_factory):
    sid = enabled(client, valid_onion_url)
    async def fetcher(_url):
        client.post(f"/api/v1/sources/{sid}/revoke", headers=API_HEADERS, json=REASON)
        return Fetched(200, "text/html", "utf-8", b"do not save")
    jid, status = asyncio.run(collect_one(uuid.UUID(sid), db_session_factory, fetcher=fetcher))
    assert status == "FAILED"
    with db_session_factory() as db:
        assert db.get(CrawlJob, jid).error_code == "AUTHORIZATION_REVOKED"
        assert db.scalar(select(func.count()).select_from(SourceObservation)) == 0


def test_jobs_unknown_and_pagination(client):
    assert client.get(f"/api/v1/collection/jobs/{uuid.uuid4()}", headers=API_HEADERS).status_code == 404
    assert client.get("/api/v1/collection/jobs?limit=0", headers=API_HEADERS).status_code == 422


def test_collection_has_no_launch_endpoint(client):
    schema = client.get("/openapi.json").json()
    assert not any(path.endswith("/launch") for path in schema["paths"])


def test_transport_refuses_compressed_body(monkeypatch, valid_onion_url):
    stream = FakeStream(payload=b"compressed")
    stream.headers["content-encoding"] = "gzip"
    monkeypatch.setattr(httpx, "AsyncClient", lambda **opts: FakeClient(stream, **opts))
    with pytest.raises(CollectError, match="ENCODING_BLOCKED"):
        asyncio.run(fetch_onion_root(valid_onion_url))


def test_no_access_on_deleted_source(client, valid_onion_url, db_session_factory):
    sid = enabled(client, valid_onion_url)
    response = client.request("DELETE", f"/api/v1/sources/{sid}", headers=API_HEADERS, json=REASON)
    assert response.status_code == 204
    with pytest.raises(NotAuthorizedError):
        async def unexpected(_url):
            raise AssertionError("Réseau jamais sollicité")
        asyncio.run(collect_one(uuid.UUID(sid), db_session_factory, fetcher=unexpected))


def test_no_duplicate_candidates_across_jobs(client, valid_onion_url, db_session_factory):
    sid = enabled(client, valid_onion_url)
    target = onion(45)
    async def fake(_url):
        return Fetched(200, "text/html", "utf-8", f'<a href="{target}">Candidate</a>'.encode())
    for _ in range(2):
        _, result = asyncio.run(collect_one(uuid.UUID(sid), db_session_factory, fetcher=fake))
        assert result == "COMPLETED"
    with db_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(DiscoveredOnion)) == 1
        assert db.scalar(select(func.count()).select_from(SourceObservation)) == 2
