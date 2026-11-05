"""M7-B2: token inventory and CLI rotation using synthetic, offline identities."""
import json
import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select

from app.models import AuditLog, Operator, OperatorToken
from app.security import manage_users
from app.security.api_key import fingerprint, new_token


def seed(factory, name, role="ANALYST", *, days=30, revoked=False):
    plaintext = new_token()
    with factory() as db:
        user = Operator(username=name, role=role)
        db.add(user)
        db.flush()
        token = OperatorToken(
            operator_id=user.id, token_hash=fingerprint(plaintext), label="laptop",
            expires_at=datetime.now(timezone.utc) + timedelta(days=days),
            revoked_at=datetime.now(timezone.utc) if revoked else None,
        )
        db.add(token)
        db.commit()
        return plaintext, token.id


def cli(monkeypatch, factory, *args):
    monkeypatch.setattr(manage_users, "session_factory", lambda: factory)
    return manage_users.main(list(args))


def test_self_inventory_only_and_metadata_without_secret(client, db_session_factory):
    secret, token_id = seed(db_session_factory, "ownanalyst")
    other, other_id = seed(db_session_factory, "someoneelse")
    response = client.get("/api/v1/auth/tokens", headers={"X-API-Key": secret})
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(token_id)
    assert body["items"][0]["label"] == "laptop"
    assert body["items"][0]["status"] == "ACTIVE"
    assert body["items"][0]["current"] is True
    assert "token_hash" not in response.text
    assert secret not in response.text and other not in response.text and str(other_id) not in response.text


def test_viewer_may_read_own_inventory(client, db_session_factory):
    secret, _ = seed(db_session_factory, "viewerone", role="VIEWER")
    assert client.get("/api/v1/auth/tokens", headers={"X-API-Key": secret}).status_code == 200
    assert client.get("/api/v1/auth/tokens", headers={"X-API-Key": "no"}).status_code == 401


def test_legacy_shared_key_cannot_list_named_tokens(client, db_session_factory):
    seed(db_session_factory, "nameduser")
    response = client.get("/api/v1/auth/tokens", headers={"X-API-Key": "local-test-only-api-key-strong-and-unique"})
    assert response.status_code == 403


def test_inventory_pagination_and_bounds(client, db_session_factory):
    secret, _ = seed(db_session_factory, "paginationuser")
    with db_session_factory() as db:
        owner = db.scalar(select(Operator).where(Operator.username == "paginationuser"))
        for _ in range(5):
            db.add(OperatorToken(operator_id=owner.id, token_hash=fingerprint(new_token()),
                                 expires_at=datetime.now(timezone.utc) + timedelta(days=3)))
        db.commit()
    h = {"X-API-Key": secret}
    assert client.get("/api/v1/auth/tokens?limit=2&offset=2", headers=h).json()["total"] == 6
    assert len(client.get("/api/v1/auth/tokens?limit=2&offset=2", headers=h).json()["items"]) == 2
    for query in ("limit=0", "limit=51", "offset=-1"):
        assert client.get("/api/v1/auth/tokens?" + query, headers=h).status_code == 422


def test_inventory_marks_revoked_and_expired(client, db_session_factory):
    current, _ = seed(db_session_factory, "statususer")
    seed(db_session_factory, "expireduser", days=-1)
    with db_session_factory() as db:
        owner = db.scalar(select(Operator).where(Operator.username == "statususer"))
        db.add(OperatorToken(operator_id=owner.id, token_hash=fingerprint(new_token()),
                             expires_at=datetime.now(timezone.utc) - timedelta(days=1)))
        db.add(OperatorToken(operator_id=owner.id, token_hash=fingerprint(new_token()),
                             expires_at=datetime.now(timezone.utc) + timedelta(days=1),
                             revoked_at=datetime.now(timezone.utc)))
        db.commit()
    data = client.get("/api/v1/auth/tokens", headers={"X-API-Key": current}).json()
    assert {item["status"] for item in data["items"]} == {"ACTIVE", "REVOKED", "EXPIRED"}


def test_rotation_atomic_revokes_old_and_audits_only_ids(monkeypatch, client, db_session_factory, capsys):
    old, old_id = seed(db_session_factory, "rotateme")
    assert cli(monkeypatch, db_session_factory, "rotate", str(old_id), "--days", "7", "--label", "workstation") == 0
    printed = capsys.readouterr().out
    new = re.search(r"API_TOKEN=(oip_[A-Za-z0-9_-]{43})", printed).group(1)
    assert new != old
    assert client.get("/api/v1/auth/me", headers={"X-API-Key": old}).status_code == 401
    assert client.get("/api/v1/auth/me", headers={"X-API-Key": new}).status_code == 200
    inventory = client.get("/api/v1/auth/tokens", headers={"X-API-Key": new}).json()
    assert [r["status"] for r in inventory["items"]].count("ACTIVE") == 1
    assert any(r["label"] == "workstation" and r["current"] for r in inventory["items"])
    with db_session_factory() as db:
        event = db.scalar(select(AuditLog).where(AuditLog.action == "operator.token.rotate"))
        assert event is not None
        assert old not in event.details and new not in event.details
        assert json.loads(event.details)["old_token_id"] == str(old_id)
        assert UUID(json.loads(event.details)["new_token_id"])


def test_rotation_rejects_expired_revoked_and_unknown_without_issuing(monkeypatch, db_session_factory, capsys):
    _, expired = seed(db_session_factory, "olddays", days=-1)
    _, revoked = seed(db_session_factory, "revokedkey", revoked=True)
    for token_id in (expired, revoked, UUID("00000000-0000-4000-8000-000000000123")):
        assert cli(monkeypatch, db_session_factory, "rotate", str(token_id)) == 1
    assert "API_TOKEN=" not in capsys.readouterr().out
    with db_session_factory() as db:
        assert db.scalar(select(OperatorToken).where(OperatorToken.id == expired)).revoked_at is None
        assert not db.scalars(select(AuditLog).where(AuditLog.action == "operator.token.rotate")).all()


def test_issue_label_and_maximum_active_tokens(monkeypatch, db_session_factory, capsys):
    seed(db_session_factory, "limiteduser")
    for i in range(4):
        assert cli(monkeypatch, db_session_factory, "issue", "limiteduser", "--label", f"device{i}") == 0
    capsys.readouterr()
    assert cli(monkeypatch, db_session_factory, "issue", "limiteduser") == 1
    output = capsys.readouterr()
    assert "Active token limit" in output.err
    assert "API_TOKEN=" not in output.out
    with db_session_factory() as db:
        owner = db.scalar(select(Operator).where(Operator.username == "limiteduser"))
        assert len(db.scalars(select(OperatorToken).where(OperatorToken.operator_id == owner.id)).all()) == 5


def test_issue_does_not_count_revoked_or_expired(monkeypatch, db_session_factory):
    seed(db_session_factory, "fewtokens")
    with db_session_factory() as db:
        owner = db.scalar(select(Operator).where(Operator.username == "fewtokens"))
        for i in range(8):
            db.add(OperatorToken(operator_id=owner.id, token_hash=fingerprint(new_token()),
                                 expires_at=datetime.now(timezone.utc) + timedelta(days=1) if i % 2 else
                                 datetime.now(timezone.utc) - timedelta(days=1),
                                 revoked_at=datetime.now(timezone.utc) if i % 2 else None))
        db.commit()
    assert cli(monkeypatch, db_session_factory, "issue", "fewtokens", "--label", "service") == 0


def test_validation_rejects_insecure_label(monkeypatch, db_session_factory):
    seed(db_session_factory, "injectionuser")
    for label in ("foo/bar", "\nsecret", "spaces in label", "X" * 65):
        try:
            cli(monkeypatch, db_session_factory, "issue", "injectionuser", "--label", label)
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError("Rejected label unexpectedly passed validation")
