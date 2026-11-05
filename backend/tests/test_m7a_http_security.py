"""M7-A: HTTP security properties and RBAC regression guard (no external network)."""

from fastapi.routing import APIRoute

from app.main import app
from app.security.api_key import require_api_key


def _dependency_tree(route: APIRoute):
    pending = [route.dependant]
    while pending:
        current = pending.pop()
        for item in current.dependencies:
            yield item.call
            pending.append(item)


def _is_role_check(dependency) -> bool:
    # require_role() returns the nested 'check' callable.
    return (
        getattr(dependency, '__module__', '') == 'app.security.api_key'
        and getattr(dependency, '__qualname__', '') == 'require_role.<locals>.check'
    )


def test_versioned_api_routes_require_authentication():
    missing = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith('/api/v1/'):
            continue
        if require_api_key not in set(_dependency_tree(route)):
            missing.append(f'{sorted(route.methods)} {route.path}')
    assert missing == [], 'Unauthenticated v1 API routes: ' + ', '.join(missing)


def test_all_mutations_require_role_guard():
    missing = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith('/api/v1/'):
            continue
        if set(route.methods) & {'POST', 'PUT', 'PATCH', 'DELETE'}:
            if not any(_is_role_check(item) for item in _dependency_tree(route)):
                missing.append(f'{sorted(route.methods)} {route.path}')
    assert missing == [], 'Missing mutation RBAC guards: ' + ', '.join(missing)


def test_sensitive_reads_require_role_guard():
    protected_prefixes = (
        '/api/v1/schedules/', '/api/v1/cases', '/api/v1/case-operations/',
    )
    protected_exact = (
        '/api/v1/collection/metrics', '/api/v1/observations/retention/preview',
        '/api/v1/cti/ioc-candidates', '/api/v1/cti/ioc-correlations',
        '/api/v1/cti/quality-preview', '/api/v1/cti/cve-ioc-links',
    )
    missing = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not (route.path.startswith(protected_prefixes) or route.path in protected_exact):
            continue
        if not any(_is_role_check(item) for item in _dependency_tree(route)):
            missing.append(route.path)
    assert missing == [], 'Sensitive reads without RBAC: ' + ', '.join(missing)


def test_fastapi_headers_cover_auth_failures_and_health(client):
    for path, status in (('/api/health', 200), ('/api/v1/auth/me', 401)):
        response = client.get(path)
        assert response.status_code == status
        for header, expected in {
            'cache-control': 'no-store',
            'x-content-type-options': 'nosniff',
            'x-frame-options': 'DENY',
            'referrer-policy': 'no-referrer',
            'cross-origin-resource-policy': 'same-origin',
            'permissions-policy': 'camera=(), microphone=(), geolocation=()',
        }.items():
            assert response.headers[header] == expected
        assert 'access-control-allow-origin' not in response.headers


def test_invalid_api_key_is_not_reflected_in_response(client):
    key = 'oip_' + 'x' * 43
    response = client.get('/api/v1/auth/me', headers={'X-API-Key': key})
    assert response.status_code == 401
    assert key not in response.text
    assert key not in str(response.headers)


def test_viewer_denied_on_every_mutation(client, db_session_factory):
    """Exercise every existing write endpoint, not merely route annotations."""
    from datetime import datetime, timedelta, timezone
    from app.models.identity import Operator, OperatorToken
    from app.security.api_key import fingerprint, new_token

    token = new_token()
    with db_session_factory() as db:
        user = Operator(username='m7_viewer', role='VIEWER')
        db.add(user)
        db.flush()
        db.add(OperatorToken(
            operator_id=user.id, token_hash=fingerprint(token),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        ))
        db.commit()
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith('/api/v1/'):
            continue
        for method in sorted(set(route.methods) & {'POST', 'PUT', 'PATCH', 'DELETE'}):
            # IDs are synthetic and do not resolve to any persisted object.
            path = route.path
            for param in route.param_convertors:
                path = path.replace('{' + param + '}', '00000000-0000-4000-8000-000000000001')
            response = client.request(method, path, headers={'X-API-Key': token}, json={})
            assert response.status_code == 403, f'{method} {path}: {response.status_code}'
