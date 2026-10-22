from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from app.models import AuditLog


def test_liveness_without_database(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "oip-api"}
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_readiness_with_database(client: TestClient):
    response = client.get("/api/ready")
    assert response.status_code == 200
    assert response.json()["database"] == "reachable"


def test_requires_api_key(client: TestClient):
    assert client.get("/api/v1/sources").status_code == 401


def test_create_and_list_source(client: TestClient, valid_onion_url: str,
                                db_session_factory: sessionmaker[Session]):
    payload = {"url": valid_onion_url[:-1].upper().replace("HTTP://", "http://"),
               "name": "Source fictive", "description": "Test local",
               "authorization_confirmed": True,
               "authorization_note": "Autorisation de test documentée"}
    result = client.post("/api/v1/sources", json=payload,
                         headers={"X-API-Key": "local-test-only-api-key-strong-and-unique"})
    assert result.status_code == 201, result.text
    assert result.json()["canonical_url"] == valid_onion_url
    assert result.json()["approved_for_collection"] is True
    assert result.json()["collection_enabled"] is False
    listing = client.get("/api/v1/sources", headers={"X-API-Key": "local-test-only-api-key-strong-and-unique"})
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert len(listing.json()["items"]) == 1
    with db_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(AuditLog)) == 1


def test_duplicate_rejected(client: TestClient, valid_onion_url: str):
    body = {"url": valid_onion_url, "name": "A", "authorization_confirmed": True,
            "authorization_note": "Autorisation enregistrée"}
    headers = {"X-API-Key": "local-test-only-api-key-strong-and-unique"}
    assert client.post("/api/v1/sources", json=body, headers=headers).status_code == 201
    assert client.post("/api/v1/sources", json=body, headers=headers).status_code == 409


def test_source_requires_explicit_authorization(client: TestClient, valid_onion_url: str):
    response = client.post("/api/v1/sources", json={
        "url": valid_onion_url, "name": "A", "authorization_confirmed": False,
        "authorization_note": "Autorisation non confirmée",
    }, headers={"X-API-Key": "local-test-only-api-key-strong-and-unique"})
    assert response.status_code == 422


def test_source_rejects_non_onion_host(client: TestClient):
    response = client.post("/api/v1/sources", json={
        "url": "http://localhost/", "name": "Non Onion",
        "authorization_confirmed": True,
        "authorization_note": "Fausse autorisation de test",
    }, headers={"X-API-Key": "local-test-only-api-key-strong-and-unique"})
    assert response.status_code == 422


def test_bad_api_key_rejected(client: TestClient):
    assert client.get("/api/v1/sources", headers={"X-API-Key": "incorrect"}).status_code == 401


def test_readiness_failure_returns_503(client: TestClient):
    from sqlalchemy.exc import OperationalError
    from app.main import app
    from app.db.session import get_session

    class BrokenSession:
        def execute(self, _statement):
            raise OperationalError("SELECT 1", (), Exception("connection lost"))

    app.dependency_overrides[get_session] = lambda: BrokenSession()
    response = client.get("/api/ready")
    assert response.status_code == 503
    assert response.json()["detail"] == "Base de données indisponible"


def test_openapi_contract(client: TestClient):
    spec = client.get("/openapi.json")
    assert spec.status_code == 200
    assert "/api/v1/sources" in spec.json()["paths"]
