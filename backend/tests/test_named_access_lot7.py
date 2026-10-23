"""RBAC, token expiration/revocation, audit identity and legacy cutover."""
from datetime import datetime, timedelta, timezone
import re

from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from app.core.config import Settings, get_settings
from app.main import app
from app.models import AuditLog, Operator, OperatorToken
from app.security.api_key import fingerprint, new_token

LEGACY = {"X-API-Key": "local-test-only-api-key-strong-and-unique"}


def _register(factory, username, role, *, days=30, revoked=False, active=True):
    token = new_token()
    with factory() as db:
        operator = Operator(username=username, role=role, active=active)
        db.add(operator)
        db.flush()
        entry = OperatorToken(operator_id=operator.id, token_hash=fingerprint(token),
                              expires_at=datetime.now(timezone.utc) + timedelta(days=days),
                              revoked_at=datetime.now(timezone.utc) if revoked else None)
        db.add(entry)
        db.commit()
    return token


def test_legacy_me_and_named_operator(client, db_session_factory):
    assert client.get('/api/v1/auth/me', headers=LEGACY).json() == {
        'username': 'legacy_operator', 'role': 'ADMIN', 'legacy': True,
    }
    key = _register(db_session_factory, 'alice', 'VIEWER')
    assert client.get('/api/v1/auth/me', headers={'X-API-Key': key}).json() == {
        'username': 'alice', 'role': 'VIEWER', 'legacy': False,
    }
    assert re.fullmatch(r'oip_[A-Za-z0-9_-]{43}', key)


def test_roles_enforced_on_actual_routes(client, db_session_factory, valid_onion_url):
    viewer = {'X-API-Key': _register(db_session_factory, 'reader', 'VIEWER')}
    analyst = {'X-API-Key': _register(db_session_factory, 'analyst', 'ANALYST')}
    admin = {'X-API-Key': _register(db_session_factory, 'admin', 'ADMIN')}
    source_payload = {'url': valid_onion_url, 'name': 'Test',
                      'authorization_confirmed': True, 'authorization_note': 'Manual approval'}
    assert client.get('/api/v1/sources', headers=viewer).status_code == 200
    assert client.post('/api/v1/sources', headers=viewer, json=source_payload).status_code == 403
    assert client.post('/api/v1/watchlists', headers=viewer, json={'name': 'My list'}).status_code == 403
    assert client.post('/api/v1/sources', headers=analyst, json=source_payload).status_code == 403
    assert client.post('/api/v1/watchlists', headers=analyst, json={'name': 'My list'}).status_code == 201
    created = client.post('/api/v1/sources', headers=admin, json=source_payload)
    assert created.status_code == 201
    assert client.post(f'/api/v1/sources/{created.json()["id"]}/collection/enable',
                       headers=analyst, json={'reason': 'Manual check'}).status_code == 403
    assert client.get('/api/v1/alerts', headers=viewer).status_code == 200
    with db_session_factory() as db:
        logs = db.scalars(select(AuditLog).where(AuditLog.action == 'source.create')).all()
        assert len(logs) == 1
        assert logs[0].actor == 'admin'
        wl = db.scalars(select(AuditLog).where(AuditLog.action == 'watchlist.create')).one()
        assert wl.actor == 'analyst'


def test_expiry_revoke_disable_and_untrusted_tokens(client, db_session_factory):
    expired = _register(db_session_factory, 'expired', 'ANALYST', days=-1)
    revoked = _register(db_session_factory, 'revoked', 'ANALYST', revoked=True)
    inactive = _register(db_session_factory, 'inactive', 'ADMIN', active=False)
    for key in (expired, revoked, inactive, new_token(), 'x' * 257):
        assert client.get('/api/v1/auth/me', headers={'X-API-Key': key}).status_code == 401
    assert client.get('/api/v1/auth/me').status_code == 401


def test_legacy_cutover(client, db_session_factory):
    named = _register(db_session_factory, 'continuing', 'ADMIN')
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url='sqlite+pysqlite://',
        api_key=SecretStr('local-test-only-api-key-strong-and-unique'),
        legacy_api_key_enabled=False,
    )
    assert client.get('/api/v1/auth/me', headers=LEGACY).status_code == 401
    assert client.get('/api/v1/auth/me', headers={'X-API-Key': named}).status_code == 200


def test_hash_never_exposes_plaintext(db_session_factory):
    secret = _register(db_session_factory, 'cryptocheck', 'VIEWER')
    with db_session_factory() as db:
        token = db.scalar(select(OperatorToken))
        assert token.token_hash != secret
        assert len(token.token_hash) == 64
        assert secret not in repr(token)
