"""Always-on, network-free guardrails for the opt-in PostgreSQL recipe."""
import os
import subprocess
from pathlib import Path

import pytest

from backend.tests.test_m7c_postgres17 import safe_test_dsn


def test_accept_only_dedicated_loopback_pg17_dsn():
    safe_test_dsn("postgresql+psycopg://oip_test:ci-only@127.0.0.1:5432/oip_m7c_test")
    safe_test_dsn("postgresql+psycopg://oip_test:ci-only@localhost/oip_m7c_test")
    safe_test_dsn("postgresql+psycopg://oip_test:ci-only@127.0.0.1:15432/oip_m7c_test")


@pytest.mark.parametrize("dsn", [
    "postgresql+psycopg://oip_test:ci-only@ovh.example/oip_m7c_test",
    "postgresql+psycopg://oip_test:ci-only@127.0.0.1/production",
    "postgresql://oip_test:ci-only@127.0.0.1/oip_m7c_test",
    "postgresql+psycopg://postgres:ci-only@127.0.0.1/oip_m7c_test",
    "postgresql+psycopg://oip_test:ci-only@127.0.0.1:5433/oip_m7c_test",
    "postgresql+psycopg://oip_test:ci-only@127.0.0.1/oip_m7c_test?sslmode=disable",
    "postgresql+psycopg://oip_test@127.0.0.1/oip_m7c_test",
])
def test_reject_unsafe_pg_dsn(dsn):
    with pytest.raises(ValueError, match="Refusing unsafe"):
        safe_test_dsn(dsn)


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "scripts" / "run-m7c-postgres17.sh"


def test_disposable_launcher_refuses_without_explicit_confirmation():
    env = {**os.environ}
    env.pop("OIP_CONFIRM_DISPOSABLE_PG17", None)
    result = subprocess.run(["bash", str(LAUNCHER)], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=5)
    assert result.returncode != 0
    assert "OIP_CONFIRM_DISPOSABLE_PG17" in result.stderr


def test_disposable_launcher_rejects_remote_docker_override():
    env = {**os.environ, "OIP_CONFIRM_DISPOSABLE_PG17": "yes",
           "DOCKER_HOST": "ssh://production.example"}
    result = subprocess.run(["bash", str(LAUNCHER)], cwd=ROOT, env=env,
                            capture_output=True, text=True, timeout=5)
    assert result.returncode != 0
    assert "Docker environment overrides" in result.stderr


def test_disposable_launcher_help_is_side_effect_free():
    result = subprocess.run(["bash", str(LAUNCHER), "--help"], cwd=ROOT,
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 0
    assert "PostgreSQL 17" in result.stdout


def test_ci_requires_real_database_integration():
    workflow = (ROOT / ".github" / "workflows" / "oip-ci.yml").read_text()
    assert "OIP_M7C_REQUIRE_DATABASE" in workflow
    assert "OIP_M4B_REQUIRE_DATABASE" in workflow
    assert "postgres17-m7c:" in workflow
    assert "postgres17-m4b:" in workflow
