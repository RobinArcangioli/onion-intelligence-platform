import base64
import hashlib
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_session
from app.main import app
from app import models  # noqa: F401


@pytest.fixture
def valid_onion_url() -> str:
    # Données entièrement synthétiques : aucun hôte réel n'est consulté.
    public_key = bytes(range(32))
    checksum = hashlib.sha3_256(b".onion checksum" + public_key + b"\x03").digest()[:2]
    host = base64.b32encode(public_key + checksum + b"\x03").decode("ascii").lower().rstrip("=")
    return f"http://{host}.onion/"


@pytest.fixture
def db_session_factory() -> Iterator[sessionmaker[Session]]:
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    engine.dispose()


@pytest.fixture
def client(db_session_factory: sessionmaker[Session]) -> Iterator[TestClient]:
    def override_session() -> Iterator[Session]:
        with db_session_factory() as db:
            yield db

    def override_settings() -> Settings:
        return Settings(database_url="sqlite+pysqlite://", api_key=SecretStr("local-test-only-api-key-strong-and-unique"))

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_settings] = override_settings
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
