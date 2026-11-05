"""OVH private-only gate blocks enqueues even for approved sources and ADMINs."""
from pydantic import SecretStr
from sqlalchemy import func, select

from app.core.config import Settings, get_settings
from app.main import app
from app.models import CrawlJob
from tests.test_manual_queue_rc2 import REASON, LEGACY, registered, enable


def test_ovh_gate_blocks_approved_manual_job(client, db_session_factory, valid_onion_url):
    sid = registered(client, valid_onion_url)
    enable(client, sid)

    def ovh_settings():
        return Settings(
            database_url="sqlite+pysqlite://",
            api_key=SecretStr("local-test-only-api-key-strong-and-unique"),
            legacy_api_key_enabled=True,
            manual_collection_enabled=False,
        )

    app.dependency_overrides[get_settings] = ovh_settings
    response = client.post(f"/api/v1/sources/{sid}/collection/run", headers=LEGACY, json=REASON)
    assert response.status_code == 503, response.text
    assert response.json()["detail"] == "Collecte manuelle désactivée sur cette instance"
    with db_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(CrawlJob)) == 0
