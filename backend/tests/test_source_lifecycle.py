"""Tests de cycle de vie hors réseau ; URLs Onion v3 entièrement synthétiques."""
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import AuditLog, OnionSource

KEY = {"X-API-Key": "local-test-only-api-key-strong-and-unique"}
REASON = {"reason": "Décision documentée par l'opérateur"}


def create(client: TestClient, url: str, name: str = "Source alpha", **kw) -> dict:
    payload = {
        "url": url, "name": name, "description": "Veille fictive locale",
        "authorization_confirmed": True,
        "authorization_note": "Autorisation vérifiée en environnement local",
        **kw,
    }
    resp = client.post("/api/v1/sources", headers=KEY, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def endpoint(source: dict, suffix: str = "") -> str:
    return f"/api/v1/sources/{source['id']}{suffix}"


def second_url(url: str) -> str:
    import base64
    import hashlib
    pub = bytes(reversed(range(32)))
    check = hashlib.sha3_256(b".onion checksum" + pub + b"\x03").digest()[:2]
    host = base64.b32encode(pub + check + b"\x03").decode().lower().rstrip("=")
    return "http://" + host + ".onion/"


def test_get_source(client: TestClient, valid_onion_url: str):
    item = create(client, valid_onion_url)
    resp = client.get(endpoint(item), headers=KEY)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Source alpha"
    assert resp.json()["priority"] == 3
    assert resp.json()["is_active"] is True
    assert resp.json()["collection_enabled"] is False
    assert "authorization_note" not in resp.json()


def test_list_pagination(client: TestClient, valid_onion_url: str):
    create(client, valid_onion_url)
    create(client, second_url(valid_onion_url), name="Source beta", priority=5)
    res = client.get("/api/v1/sources?limit=1&offset=1", headers=KEY)
    assert res.status_code == 200
    assert res.json()["total"] == 2
    assert len(res.json()["items"]) == 1
    assert res.json()["limit"] == 1
    assert res.json()["offset"] == 1


@pytest.mark.parametrize("query,expected", [
    ("q=alpha", 1), ("q=BETA", 1), ("q=absent", 0),
    ("approved=true", 2), ("approved=false", 0),
    ("active=true", 2), ("active=false", 0),
    ("priority=5", 1), ("priority=3", 1),
    ("category=UNKNOWN", 2), ("category=NEWS", 0),
    ("q=%25", 0), ("q=%5F", 0),
])
def test_list_filters(client: TestClient, valid_onion_url: str, query: str, expected: int):
    create(client, valid_onion_url)
    create(client, second_url(valid_onion_url), name="Source beta", priority=5)
    res = client.get("/api/v1/sources?" + query, headers=KEY)
    assert res.status_code == 200
    assert res.json()["total"] == expected


@pytest.mark.parametrize("q", ["limit=101", "offset=-1", "priority=7", "q=", "q=%20%20%20"])
def test_list_invalid_filters(client: TestClient, q: str):
    assert client.get("/api/v1/sources?" + q, headers=KEY).status_code == 422


def test_patch_and_filter(client: TestClient, valid_onion_url: str):
    s = create(client, valid_onion_url)
    res = client.patch(endpoint(s), headers=KEY, json={
        "name": "Nom nouveau", "description": "Nouveau texte", "category": "CYBERCRIME_FORUM",
        "priority": 1, "reason": "Mise à jour après révision manuelle",
    })
    assert res.status_code == 200, res.text
    assert res.json()["category"] == "CYBERCRIME_FORUM"
    assert res.json()["priority"] == 1
    assert client.get("/api/v1/sources?category=CYBERCRIME_FORUM&priority=1", headers=KEY).json()["total"] == 1
    history = client.get(endpoint(s, "/history"), headers=KEY).json()
    assert history["total"] == 2
    audit = next(x for x in history["items"] if x["action"] == "source.update")
    assert audit["details"]["fields"] == ["category", "description", "name", "priority"]
    assert "Nouveau texte" not in json.dumps(audit)


@pytest.mark.parametrize("patch", [
    {"url": "http://another.onion/"},
    {"collection_enabled": True},
    {"approved_for_collection": True},
    {"is_active": False},
    {"category": "bad-value"},
    {"priority": 0},
    {"name": "  "},
    {},
])
def test_patch_cannot_change_protected_fields(client: TestClient, valid_onion_url: str, patch: dict):
    s = create(client, valid_onion_url)
    result = client.patch(endpoint(s), headers=KEY, json={**patch, "reason": "Une justification de dix caractères"})
    assert result.status_code == 422


def test_noop_patch_no_audit(client: TestClient, valid_onion_url: str):
    s = create(client, valid_onion_url)
    res = client.patch(endpoint(s), headers=KEY, json={"name": "Source alpha", "reason": "Justification de contrôle de non-changement"})
    assert res.status_code == 200
    assert client.get(endpoint(s, "/history"), headers=KEY).json()["total"] == 1


def test_deactivate_activate(client: TestClient, valid_onion_url: str):
    s = create(client, valid_onion_url)
    assert client.post(endpoint(s, "/deactivate"), headers=KEY, json=REASON).json()["is_active"] is False
    assert client.get("/api/v1/sources?active=false", headers=KEY).json()["total"] == 1
    result = client.post(endpoint(s, "/activate"), headers=KEY, json=REASON)
    assert result.status_code == 200
    assert result.json()["is_active"] is True
    assert result.json()["collection_enabled"] is False
    assert client.get(endpoint(s, "/history"), headers=KEY).json()["total"] == 3


def test_revoke_then_reapprove(client: TestClient, valid_onion_url: str):
    s = create(client, valid_onion_url)
    resp = client.post(endpoint(s, "/revoke"), headers=KEY, json=REASON)
    assert resp.status_code == 200
    assert resp.json()["approved_for_collection"] is False
    assert resp.json()["collection_enabled"] is False
    assert client.get("/api/v1/sources?approved=false", headers=KEY).json()["total"] == 1
    assert client.post(endpoint(s, "/approve"), headers=KEY, json={
        "authorization_confirmed": False,
        "authorization_note": "Tentative sans autorisation explicite",
    }).status_code == 422
    resp = client.post(endpoint(s, "/approve"), headers=KEY, json={
        "authorization_confirmed": True,
        "authorization_note": "Nouvelle autorisation documentée pour tests",
    })
    assert resp.status_code == 200
    assert resp.json()["approved_for_collection"] is True
    assert resp.json()["collection_enabled"] is False
    assert client.get(endpoint(s, "/history"), headers=KEY).json()["total"] == 3


def test_delete_restore_requires_reapproval(client: TestClient, valid_onion_url: str):
    s = create(client, valid_onion_url)
    deleted = client.request("DELETE", endpoint(s), headers=KEY, json=REASON)
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert client.get(endpoint(s), headers=KEY).status_code == 404
    assert client.get("/api/v1/sources", headers=KEY).json()["total"] == 0
    assert client.post("/api/v1/sources", headers=KEY, json={
        "url": valid_onion_url, "name": "Duplicata", "authorization_confirmed": True,
        "authorization_note": "Autorisation fictive pour tests",
    }).status_code == 409
    assert client.get(endpoint(s, "/history"), headers=KEY).json()["total"] == 2
    restored = client.post(endpoint(s, "/restore"), headers=KEY, json=REASON)
    assert restored.status_code == 200
    assert restored.json()["is_active"] is False
    assert restored.json()["approved_for_collection"] is False
    assert restored.json()["collection_enabled"] is False
    assert restored.json()["deleted_at"] is None
    assert client.post(endpoint(s, "/restore"), headers=KEY, json=REASON).status_code == 409
    assert client.get(endpoint(s, "/history"), headers=KEY).json()["total"] == 3


def test_history_pagination(client: TestClient, valid_onion_url: str):
    s = create(client, valid_onion_url)
    client.post(endpoint(s, "/revoke"), headers=KEY, json=REASON)
    res = client.get(endpoint(s, "/history?limit=1&offset=1"), headers=KEY)
    assert res.status_code == 200
    assert res.json()["total"] == 2
    assert len(res.json()["items"]) == 1
    assert res.json()["limit"] == 1
    assert res.json()["offset"] == 1


@pytest.mark.parametrize("method,suffix,jsonbody", [
    ("GET", "", None),
    ("PATCH", "", {"name": "No", "reason": "Justification suffisamment longue"}),
    ("DELETE", "", REASON),
    ("POST", "/revoke", REASON),
    ("POST", "/approve", {"authorization_confirmed": True, "authorization_note": "Autorisation de test valide"}),
    ("POST", "/activate", REASON),
    ("POST", "/deactivate", REASON),
    ("POST", "/restore", REASON),
    ("GET", "/history", None),
])
def test_all_routes_require_api_key(client: TestClient, valid_onion_url: str, method: str, suffix: str, jsonbody: dict | None):
    s = create(client, valid_onion_url)
    result = client.request(method, endpoint(s, suffix), json=jsonbody)
    assert result.status_code == 401


def test_unknown_id(client: TestClient):
    missing = f"/api/v1/sources/{uuid.uuid4()}"
    assert client.get(missing, headers=KEY).status_code == 404
    assert client.get(missing + "/history", headers=KEY).status_code == 404
    assert client.patch(missing, headers=KEY, json={
        "name": "Nouveau", "reason": "Justification de modification",
    }).status_code == 404


def test_invalid_id(client: TestClient):
    assert client.get("/api/v1/sources/not-a-uuid", headers=KEY).status_code == 422


def test_audit_is_transactional_and_no_secret(client: TestClient, valid_onion_url: str,
                                              db_session_factory: sessionmaker[Session]):
    s = create(client, valid_onion_url)
    client.post(endpoint(s, "/revoke"), headers=KEY, json=REASON)
    with db_session_factory() as db:
        audits = db.scalars(select(AuditLog).where(AuditLog.entity_id == uuid.UUID(s["id"]))).all()
        assert len(audits) == 2
        assert all("local-test-only-api-key" not in row.details for row in audits)
        assert db.scalar(select(func.count()).select_from(OnionSource)) == 1


def test_openapi_declares_all_routes(client: TestClient):
    paths = client.get("/openapi.json").json()["paths"]
    for endpoint_ in (
        "/api/v1/sources/{source_id}", "/api/v1/sources/{source_id}/revoke",
        "/api/v1/sources/{source_id}/approve", "/api/v1/sources/{source_id}/history",
        "/api/v1/sources/{source_id}/restore",
    ):
        assert endpoint_ in paths


def test_decision_requires_reason(client: TestClient, valid_onion_url: str):
    s = create(client, valid_onion_url)
    assert client.post(endpoint(s, "/revoke"), headers=KEY, json={"reason": "short"}).status_code == 422
    assert client.request("DELETE", endpoint(s), headers=KEY).status_code == 422


def test_bulk_import_and_export(client: TestClient, valid_onion_url: str):
    urls = [valid_onion_url, second_url(valid_onion_url)]
    body = {"items": [{
        "url": url, "name": "=SUM(1+1)" if n == 0 else "Beta",
        "authorization_confirmed": True,
        "authorization_note": "Test d'import explicitement autorisé",
    } for n, url in enumerate(urls)]}
    response = client.post("/api/v1/sources/import", headers=KEY, json=body)
    assert response.status_code == 201, response.text
    assert response.json()["total"] == 2
    assert all(not item["collection_enabled"] for item in response.json()["items"])
    exported = client.get("/api/v1/sources/export.csv", headers=KEY)
    assert exported.status_code == 200
    assert "text/csv" in exported.headers["content-type"]
    assert "'=SUM(1+1)" in exported.text
    assert "authorization_note" not in exported.text
    assert "Test d'import explicitement autorisé" not in exported.text


def test_bulk_import_atomic_duplicate(client: TestClient, valid_onion_url: str):
    item = {"url": valid_onion_url, "name": "Test import", "authorization_confirmed": True,
            "authorization_note": "Autorisation de test documentée"}
    res = client.post("/api/v1/sources/import", headers=KEY, json={"items": [item, item]})
    assert res.status_code == 409
    assert client.get("/api/v1/sources", headers=KEY).json()["total"] == 0


def test_bulk_import_atomic_existing_source(client: TestClient, valid_onion_url: str):
    create(client, valid_onion_url)
    items = [
        {"url": url, "name": "Import", "authorization_confirmed": True,
         "authorization_note": "Autorisation de test documentée"}
        for url in [second_url(valid_onion_url), valid_onion_url]
    ]
    res = client.post("/api/v1/sources/import", headers=KEY, json={"items": items})
    assert res.status_code == 409
    assert client.get("/api/v1/sources", headers=KEY).json()["total"] == 1


@pytest.mark.parametrize("endpoint_, method,body", [
    ("/api/v1/sources/import", "POST", {"items": []}),
    ("/api/v1/sources/export.csv", "GET", None),
])
def test_bulk_endpoints_are_protected(client: TestClient, endpoint_: str, method: str, body: dict | None):
    result = client.request(method, endpoint_, json=body)
    assert result.status_code == 401


def test_import_rejects_unconfirmed_authorization(client: TestClient, valid_onion_url: str):
    res = client.post("/api/v1/sources/import", headers=KEY, json={"items": [{
        "url": valid_onion_url, "name": "Test import", "authorization_confirmed": False,
        "authorization_note": "Autorisation de test documentée",
    }]})
    assert res.status_code == 422


@pytest.mark.parametrize("note", ["X          ", "          X"])
def test_authorization_note_rejects_whitespace_padding(client: TestClient, valid_onion_url: str, note: str):
    res = client.post("/api/v1/sources", headers=KEY, json={
        "url": valid_onion_url, "name": "Source", "authorization_confirmed": True,
        "authorization_note": note,
    })
    assert res.status_code == 422


def test_patch_reason_rejects_whitespace_padding(client: TestClient, valid_onion_url: str):
    s = create(client, valid_onion_url)
    result = client.patch(endpoint(s), headers=KEY, json={"name": "Rename", "reason": "X          "})
    assert result.status_code == 422
