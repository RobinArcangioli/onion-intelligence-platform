"""Fail closed if a future Compose edit accidentally publishes Tor or DB ports."""
from pathlib import Path
import os
import ast

import yaml
from fastapi.routing import APIRoute

from app.main import app

# Outside Docker, locate the repository from this file. Under Docker Compose,
# non-secret deployment configuration is mounted read-only at /app.
ROOT = Path(os.environ.get('OIP_TEST_REPO_ROOT', str(Path(__file__).resolve().parents[2])))


def test_only_gateway_has_published_loopback_port():
    config = yaml.safe_load((ROOT / 'compose.yaml').read_text())
    services = config['services']
    for name in ('db', 'api', 'collector', 'tor'):
        assert not services[name].get('ports'), name
    assert services['gateway']['ports'] == ['127.0.0.1:8000:8080']
    assert 'tor_egress' not in services['collector']['networks']
    assert 'ingress' not in services['collector']['networks']
    assert services['collector']['networks'] == ['private', 'tor_proxy']
    assert config['networks']['tor_proxy']['internal'] is True
    assert config['networks']['private']['internal'] is True
    assert services['tests']['network_mode'] == 'none'


def test_all_data_mutation_endpoints_have_role_dependency():
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith('/api/v1/'):
            continue
        if not ({'POST', 'PATCH', 'PUT', 'DELETE'} & route.methods):
            continue
        # Nested closure named 'check' returned from require_role().
        assert any(dep.call.__name__ == 'check' for dep in route.dependant.dependencies), route.path


def test_backups_are_secret_free_in_source_control():
    for script in ('scripts/backup-db.sh', 'scripts/restore-db.sh'):
        source = (ROOT / script).read_text()
        assert 'pg_' in source
        assert 'POSTGRES_PASSWORD=' not in source
        assert 'umask 077' in source
