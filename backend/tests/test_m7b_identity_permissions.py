"""M7-B resource permissions and token lifecycle, synthetic local DB only."""
import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import AuditLog, Operator, OperatorToken
from app.security.api_key import fingerprint, new_token
from app.security import manage_users
from backend.tests.test_m6a_cases import create, person, update

LEGACY = {"X-API-Key": "local-test-only-api-key-strong-and-unique"}


def _seed(factory, name, role="ADMIN", active=True):
    key = new_token()
    with factory() as db:
        user = Operator(username=name, role=role, active=active)
        db.add(user)
        db.flush()
        db.add(OperatorToken(operator_id=user.id, token_hash=fingerprint(key),
                             expires_at=datetime.now(timezone.utc) + timedelta(days=30)))
        db.commit()
    return {"X-API-Key": key}


def _command(monkeypatch, factory, *argv):
    monkeypatch.setattr(manage_users, "session_factory", lambda: factory)
    return manage_users.main(list(argv))


def test_analyst_can_only_claim_unassigned_for_self(client, db_session_factory):
    alice = person(db_session_factory, "m7alice")
    bob = person(db_session_factory, "m7bob")
    row = create(client, db_session_factory)
    assert update(client, row, "ASSIGN", headers=bob, assignee_username="m7alice").status_code == 403
    claimed = update(client, row, "ASSIGN", headers=alice, assignee_username="m7alice")
    assert claimed.status_code == 200
    row = claimed.json()
    assert update(client, row, "UNASSIGN", headers=bob).status_code == 403
    assert update(client, row, "SET_PRIORITY", headers=bob, priority="HIGH").status_code == 403
    assert update(client, row, "ASSIGN", headers=bob, assignee_username="m7bob").status_code == 403
    advanced = update(client, row, "START_REVIEW", headers=alice)
    assert advanced.status_code == 200
    assert update(client, advanced.json(), "UNASSIGN", headers=LEGACY).status_code == 200


def test_analyst_cannot_annotate_someone_elses_case(client, db_session_factory):
    alice = person(db_session_factory, "m7alicia")
    bob = person(db_session_factory, "m7robert")
    row = create(client, db_session_factory)
    assigned = update(client, row, "ASSIGN", headers=alice, assignee_username="m7alicia").json()
    path = f"/api/v1/cases/{row['id']}/notes"
    payload = {"expected_version": assigned["version"], "note_code": "FOLLOW_UP", "body": "Test metadata only."}
    # Validations may vary by schema, so inspect authorization before accepting a note.
    response = client.post(path, headers=bob, json=payload)
    assert response.status_code == 403
    assert client.get(path, headers=bob).status_code == 200  # team-wide read policy is unchanged
    assert client.get(path, headers=alice).json()["total"] == 0


def test_admin_can_reassign_and_old_owner_loses_write_access(client, db_session_factory):
    alice = person(db_session_factory, "m7oldowner")
    bob = person(db_session_factory, "m7newowner")
    row = create(client, db_session_factory)
    first = update(client, row, "ASSIGN", headers=alice, assignee_username="m7oldowner").json()
    reassigned = update(client, first, "ASSIGN", headers=LEGACY, assignee_username="m7newowner")
    assert reassigned.status_code == 200
    current = reassigned.json()
    assert update(client, current, "START_REVIEW", headers=alice).status_code == 403
    assert update(client, current, "START_REVIEW", headers=bob).status_code == 200
    assert update(client, first, "START_REVIEW", headers=bob).status_code == 409


def test_cli_cannot_disable_or_demote_last_active_admin(monkeypatch, db_session_factory, capsys):
    admin = _seed(db_session_factory, "soleadmin")
    assert _command(monkeypatch, db_session_factory, "disable", "soleadmin") == 1
    assert _command(monkeypatch, db_session_factory, "set-role", "soleadmin", "--role", "VIEWER") == 1
    with db_session_factory() as db:
        user = db.scalar(select(Operator).where(Operator.username == "soleadmin"))
        assert user.active and user.role == "ADMIN"
        assert db.scalar(select(OperatorToken).where(OperatorToken.operator_id == user.id)).revoked_at is None
    assert "last active administrator" in capsys.readouterr().err


def test_cli_role_change_revokes_all_tokens_and_audits(monkeypatch, client, db_session_factory, capsys):
    _seed(db_session_factory, "superadmin")
    alice = _seed(db_session_factory, "m7promote", "VIEWER")
    assert client.get("/api/v1/auth/me", headers=alice).status_code == 200
    assert _command(monkeypatch, db_session_factory, "set-role", "m7promote", "--role", "ANALYST") == 0
    assert client.get("/api/v1/auth/me", headers=alice).status_code == 401
    with db_session_factory() as db:
        user = db.scalar(select(Operator).where(Operator.username == "m7promote"))
        assert user.role == "ANALYST"
        tokens = db.scalars(select(OperatorToken).where(OperatorToken.operator_id == user.id)).all()
        assert tokens and all(t.revoked_at is not None for t in tokens)
        audit = db.scalar(select(AuditLog).where(AuditLog.action == "operator.role_change"))
        assert json.loads(audit.details)["tokens_revoked"] == 1
        assert "oip_" not in audit.details
    assert "revoked_tokens=1" in capsys.readouterr().out


def test_disable_enable_never_restores_old_token(monkeypatch, client, db_session_factory):
    _seed(db_session_factory, "anotheradmin")
    old_key = _seed(db_session_factory, "rotateadmin")
    assert _command(monkeypatch, db_session_factory, "disable", "rotateadmin") == 0
    assert client.get("/api/v1/auth/me", headers=old_key).status_code == 401
    assert _command(monkeypatch, db_session_factory, "enable", "rotateadmin") == 0
    assert client.get("/api/v1/auth/me", headers=old_key).status_code == 401
    assert _command(monkeypatch, db_session_factory, "set-role", "rotateadmin", "--role", "VIEWER") == 0
    assert client.get("/api/v1/auth/me", headers=old_key).status_code == 401


def test_last_admin_can_be_changed_with_another_active_admin(monkeypatch, db_session_factory):
    _seed(db_session_factory, "firstadmin")
    _seed(db_session_factory, "secondadmin")
    assert _command(monkeypatch, db_session_factory, "set-role", "firstadmin", "--role", "ANALYST") == 0
    assert _command(monkeypatch, db_session_factory, "disable", "secondadmin") == 1
