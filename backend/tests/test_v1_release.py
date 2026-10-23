"""Release candidate gates, synthetic config only; no Tor or registry access."""
import json
import os
from pathlib import Path
import subprocess
import sys

from pydantic import SecretStr

from app.core.config import Settings

ROOT = Path(os.environ.get('OIP_TEST_REPO_ROOT', str(Path(__file__).resolve().parents[2])))


def test_legacy_access_disabled_by_default():
    # Existing .env may still opt in; release validation separately rejects that.
    assert Settings.model_fields['legacy_api_key_enabled'].default is False


def test_release_config_check_rejects_published_collector_port():
    script = ROOT / 'scripts/check-release-config.py'
    assert script.exists()
    config = {
        'services': {
            'db': {}, 'api': {}, 'tor': {}, 'collector': {'networks': {'private': {}, 'tor_proxy': {}}},
            'queue_worker': {'networks': {'private': {}, 'tor_proxy': {}}, 'profiles': ['tor'], 'read_only': True, 'cap_drop': ['ALL']},
            'tests': {'network_mode': 'none'},
            'gateway': {'ports': [{'host_ip': '127.0.0.1', 'published': '8000', 'target': 8080}]},
        },
        'networks': {'private': {'internal': True}, 'tor_proxy': {'internal': True}},
    }
    command = [sys.executable, str(script)]
    good = subprocess.run(command, input=json.dumps(config), capture_output=True, text=True, check=False)
    assert good.returncode == 0
    assert 'PASS:' in good.stdout
    config['services']['collector']['ports'] = [{'host_ip': '0.0.0.0', 'published': '9050', 'target': 9050}]
    bad = subprocess.run(command, input=json.dumps(config), capture_output=True, text=True, check=False)
    assert bad.returncode != 0
    assert 'collector publishes' in bad.stderr


def test_release_validator_loads_all_compose_profiles():
    # ``docker compose config`` without profiles omits tor, collector and tests.
    # All three must be visible to the isolation policy gate.
    release = (ROOT / 'scripts/validate-v1.sh').read_text(encoding='utf-8')
    assert 'docker compose --profile tor --profile test config --quiet' in release
    assert ('docker compose --profile tor --profile test config --format json '
            '| python3 scripts/check-release-config.py') in release


def test_release_gate_is_non_destructive():
    release = (ROOT / 'scripts/validate-v1.sh').read_text(encoding='utf-8')
    assert 'scripts/check-network-isolation.sh' in release
    assert 'scripts/check-backup-restore.sh' in release
    assert 'scripts/restore-db.sh' not in release
    assert 'source .env' not in release
    assert 'cat .env' not in release
    assert 'OIP_LEGACY_API_KEY_ENABLED=false' in release
    assert '--release' in release


def test_compose_disables_legacy_by_default_and_collector_stays_private():
    compose = (ROOT / 'compose.yaml').read_text(encoding='utf-8')
    assert 'OIP_LEGACY_API_KEY_ENABLED:-false' in compose
    assert 'network_mode: none' in compose
    assert 'networks: [private, tor_proxy]' in compose


def test_build_prefers_npm_ci_when_lock_is_present():
    dockerfile = (ROOT / 'frontend/Dockerfile').read_text(encoding='utf-8')
    assert 'npm ci --no-audit --no-fund' in dockerfile
    assert 'package-lock.json' in dockerfile


def test_named_operator_setting_is_explicit():
    cfg = Settings(database_url='sqlite+pysqlite://',
                   api_key=SecretStr('local-test-only-api-key-strong-and-unique'))
    assert cfg.legacy_api_key_enabled is False


def test_frontend_unit_tests_run_without_experimental_node_type_stripping():
    # Docker's backend-only build context excludes frontend/. Compose binds only
    # the two non-secret files needed for this cross-component contract check.
    package_path = Path(os.environ.get(
        'OIP_TEST_FRONTEND_PACKAGE', str(ROOT / 'frontend/package.json')
    ))
    loader_path = Path(os.environ.get(
        'OIP_TEST_FRONTEND_TS_LOADER', str(ROOT / 'frontend/tests/ts-loader.mjs')
    ))
    package = json.loads(package_path.read_text(encoding='utf-8'))
    command = package['scripts']['test:unit']
    assert '--experimental-strip-types' not in command
    assert '--loader ./tests/ts-loader.mjs' in command
    assert loader_path.is_file()


def test_release_reuses_sudo_callers_playwright_browser_cache():
    script = (ROOT / 'scripts/validate-v1.sh').read_text(encoding='utf-8')
    assert 'SUDO_USER' in script
    assert 'PLAYWRIGHT_BROWSERS_PATH' in script
    assert 'ms-playwright' in script
