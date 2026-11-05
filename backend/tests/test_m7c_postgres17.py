"""M7-C PostgreSQL 17 rehearsal. NEVER point this at OIP production.

Opt-in only: OIP_M7C_TEST_DSN must name an EMPTY local 'oip_m7c_test'
database. All rows, names and tokens are synthetic. No Tor or external IO.
"""
from __future__ import annotations

import itertools
import os
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier, Lock

import pytest
from sqlalchemy import create_engine, func, inspect, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.models import Alert, AnalystCase, CrawlJob, OnionSource, Operator, OperatorToken, SourceObservation
from app.security import manage_users
from app.security.api_key import fingerprint

BACKEND = Path(__file__).resolve().parents[1]
EXPECTED_DB = "oip_m7c_test"
REVISION = "0017_case_notification_drafts"


def safe_test_dsn(raw: str):
    """Fail closed before creating a DB engine or invoking Alembic."""
    url = make_url(raw)
    if (url.drivername != "postgresql+psycopg" or url.database != EXPECTED_DB
            or url.host not in ("127.0.0.1", "localhost", "::1")
            or (url.port not in (None, 5432, 15432)) or url.query
            or url.username != "oip_test" or not url.password):
        raise ValueError("Refusing unsafe M7-C PostgreSQL test DSN")
    return url


def migrate(dsn: str, *args: str):
    env = {**os.environ, "OIP_DATABASE_URL": dsn}
    outcome = subprocess.run([sys.executable, "-m", "alembic", *args], cwd=BACKEND,
                             env=env, capture_output=True, text=True, timeout=120)
    # Do not echo subprocess output: may contain credentials in connection strings.
    assert outcome.returncode == 0, f"Alembic {args!r} failed (see guarded local logs)"


@pytest.fixture(scope="module")
def pg_factory():
    dsn = os.environ.get("OIP_M7C_TEST_DSN")
    if not dsn:
        if os.environ.get("OIP_M7C_REQUIRE_DATABASE") == "1":
            pytest.fail("PostgreSQL 17 integration was required but OIP_M7C_TEST_DSN is missing")
        pytest.skip("Requires opt-in disposable local PostgreSQL 17 test database")
    safe_test_dsn(dsn)
    engine = create_engine(dsn, pool_pre_ping=True,
                           connect_args={"options": "-c statement_timeout=20000 -c lock_timeout=8000"})
    try:
        with engine.connect() as conn:
            assert conn.dialect.server_version_info[0] == 17
            assert conn.scalar(text("SELECT COUNT(*) FROM information_schema.tables "
                                    "WHERE table_schema='public' AND table_type='BASE TABLE'")) == 0, (
                "Test database MUST be empty; refusing to alter existing schema")
        # Rehearse entire additive chain and reversible last migration before any test rows.
        migrate(dsn, "upgrade", "head")
        with engine.connect() as conn:
            assert conn.scalar(text("SELECT version_num FROM alembic_version")) == REVISION
            assert inspect(conn).has_table("case_notification_drafts")
        migrate(dsn, "downgrade", "0016_case_triage_notes")
        with engine.connect() as conn:
            assert not inspect(conn).has_table("case_notification_drafts")
        migrate(dsn, "upgrade", "head")
        yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    finally:
        engine.dispose()


def _operator(factory, name: str, role: str, *, tokens: int = 0):
    with factory() as db:
        op = Operator(username=name, role=role)
        db.add(op)
        db.flush()
        for index in range(tokens):
            db.add(OperatorToken(operator_id=op.id,
                                 token_hash=fingerprint(f"synthetic-m7c-{name}-{index}"),
                                 expires_at=datetime.now(timezone.utc) + timedelta(days=7)))
        db.commit()
        return op.id


def _fake_issuance(monkeypatch, factory):
    monkeypatch.setattr(manage_users, "session_factory", lambda: factory)
    sequence = itertools.count(1)
    lock = Lock()

    def fake_token():
        # Known deterministic test-only marker; NEVER create usable real tokens in CI.
        with lock:
            return f"CI_SYNTHETIC_NOT_A_LOGIN_TOKEN_{next(sequence)}"

    monkeypatch.setattr(manage_users, "new_token", fake_token)


def test_postgres17_version_and_new_indexes(pg_factory):
    with pg_factory() as db:
        assert db.scalar(text("SELECT version_num FROM alembic_version")) == REVISION
        for table in ("operator_tokens", "analyst_cases", "case_notification_policies",
                      "case_notification_drafts", "ioc_candidates", "source_schedules"):
            assert inspect(db.connection()).has_table(table)
        assert db.scalar(text("SELECT COUNT(*) FROM pg_indexes WHERE schemaname='public' "
                              "AND indexname='ix_observation_metadata_search'")) == 1


def test_two_admins_cannot_both_disable_in_parallel(monkeypatch, pg_factory):
    _fake_issuance(monkeypatch, pg_factory)
    a = f"admin{uuid.uuid4().hex[:9]}"
    b = f"admin{uuid.uuid4().hex[:9]}"
    a_id = _operator(pg_factory, a, "ADMIN")
    b_id = _operator(pg_factory, b, "ADMIN")
    barrier = Barrier(2)

    def disable(username):
        barrier.wait(timeout=8)
        return manage_users.main(["disable", username])

    with ThreadPoolExecutor(max_workers=2) as pool:
        r1 = pool.submit(disable, a)
        r2 = pool.submit(disable, b)
        assert sorted([r1.result(timeout=25), r2.result(timeout=25)]) == [0, 1]
    with pg_factory() as db:
        assert db.scalar(select(func.count()).select_from(Operator).where(
            Operator.id.in_([a_id, b_id]), Operator.role == "ADMIN",
            Operator.active.is_(True))) == 1


def test_token_quota_atomic_with_two_issuers(monkeypatch, pg_factory):
    _fake_issuance(monkeypatch, pg_factory)
    name = f"user{uuid.uuid4().hex[:10]}"
    user_id = _operator(pg_factory, name, "VIEWER", tokens=4)
    barrier = Barrier(2)

    def issue():
        barrier.wait(timeout=8)
        return manage_users.main(["issue", name, "--days", "7", "--label", "ci-test"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(issue)
        f2 = pool.submit(issue)
        assert sorted([f1.result(timeout=25), f2.result(timeout=25)]) == [0, 1]
    with pg_factory() as db:
        assert db.scalar(select(func.count()).select_from(OperatorToken).where(
            OperatorToken.operator_id == user_id, OperatorToken.revoked_at.is_(None),
            OperatorToken.expires_at > datetime.now(timezone.utc))) == 5


def test_case_version_compare_and_swap_in_postgres(pg_factory):
    """Two sessions may read version 1, but exactly one can commit version 2."""
    with pg_factory() as db:
        source = OnionSource(canonical_url=f"http://fixture-{uuid.uuid4().hex}.onion/",
                             name="M7C synthetic", authorization_note="Test-only fixture")
        db.add(source)
        db.flush()
        job = CrawlJob(source_id=source.id, status="COMPLETED")
        db.add(job)
        db.flush()
        observation = SourceObservation(job_id=job.id, source_id=source.id,
                                        http_status=200, content_type="text/plain",
                                        response_bytes=5, text_sha256="c" * 64, text_length=5)
        db.add(observation)
        db.flush()
        alert = Alert(source_id=source.id, observation_id=observation.id,
                      fingerprint=uuid.uuid4().hex, event_type="DOCUMENTARY_SIGNAL",
                      signal_code="SYNTHETIC", priority="LOW",
                      verification_status="UNVERIFIED", relevance_score=1)
        db.add(alert)
        db.flush()
        case = AnalystCase(alert_id=alert.id, created_by="ci_test")
        db.add(case)
        db.commit()
        case_id = case.id
    barrier = Barrier(2)

    def change(priority):
        with pg_factory() as db:
            observed = db.get(AnalystCase, case_id).version
            assert observed == 1
            barrier.wait(timeout=8)
            count = db.execute(update(AnalystCase).where(
                AnalystCase.id == case_id, AnalystCase.version == observed).values(
                version=observed + 1, priority=priority)).rowcount
            db.commit()
            return count

    with ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(change, "HIGH")
        f2 = pool.submit(change, "LOW")
        assert sorted([f1.result(timeout=25), f2.result(timeout=25)]) == [0, 1]
    with pg_factory() as db:
        row = db.get(AnalystCase, case_id)
        assert row.version == 2 and row.priority in ("HIGH", "LOW")
