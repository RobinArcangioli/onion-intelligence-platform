"""Operator capture and routine collection share the real analysis and report flow."""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.collector.transport import Fetched
from app.collector.worker import process_one

HEADERS = {"X-API-Key": "local-test-only-api-key-strong-and-unique"}
REASON = {"reason": "Local marketplace acceptance"}


def source(client, url):
    response = client.post("/api/v1/sources", headers=HEADERS, json={
        "url": url, "name": "Synthetic marketplace", "authorization_confirmed": True,
        "authorization_note": "Approved synthetic marketplace",
    })
    assert response.status_code == 201, response.text
    return "/api/v1/sources/" + response.json()["id"]


def test_capture_and_routine_group_collection(client, db_session_factory, valid_onion_url, monkeypatch):
    monkeypatch.setenv("OIP_COLLECTION_MAX_PENDING", "1")
    begin = datetime.now(timezone.utc) - timedelta(minutes=5)
    root = valid_onion_url
    blocked = root + "blocked"
    catalog = root + "catalogue"
    group = source(client, root)
    pages = group + "/pages"
    assert client.post(pages, headers=HEADERS, json={"url": blocked}).status_code == 200
    watchlist = client.post("/api/v1/watchlists", headers=HEADERS, json={"name": "Synthetic rules"}).json()["id"]
    assert client.post(f"/api/v1/watchlists/{watchlist}/rules", headers=HEADERS,
                       json={"phrase": "cannabis", "weight": 15}).status_code == 201
    assert client.get("/api/v1/collection/jobs", headers=HEADERS).json()["total"] == 0
    payload = {"url": catalog, "text": "Synthetic cannabis catalogue CAPTURE_RAW_SENTINEL",
               "request_id": str(uuid4())}
    rejected = client.post(pages + "/capture", headers=HEADERS, json={**payload, "url": catalog + "?session=secret"})
    assert rejected.status_code == 422 and "CAPTURE_RAW_SENTINEL" not in rejected.text
    capture = client.post(pages + "/capture", headers=HEADERS, json=payload)
    assert capture.status_code == 200, capture.text
    observed = capture.json()
    assert observed["origin"] == "OPERATOR_CAPTURE" and observed["http_status"] is None
    assert "CAPTURE_RAW_SENTINEL" not in capture.text
    with db_session_factory() as db:
        sqlite = db.connection().connection.driver_connection
        assert not any("CAPTURE_RAW_SENTINEL" in line for line in sqlite.iterdump())
    assert client.post(pages + "/capture", headers=HEADERS, json=payload).json()["id"] == observed["id"]
    assert client.get("/api/public/v1/activity").json()["total"] == 0
    alert = client.get("/api/v1/alerts", headers=HEADERS).json()["items"][0]
    assert alert["observation_id"] == observed["id"] and alert["event_type"] == "WATCHLIST_MATCH"
    assert client.post(group + "/collection/enable", headers=HEADERS, json=REASON).status_code == 200
    assert client.post(group + "/collection/run", headers=HEADERS, json=REASON).status_code == 202
    assert client.post(group + "/collection/run", headers=HEADERS, json=REASON).status_code == 409

    seen = []

    async def fake_fetch(url):
        seen.append(url)
        if url == blocked:
            return Fetched(200, "text/html", "utf-8", b"<p>Checking your browser. Please wait.</p>")
        return Fetched(200, "text/plain", "utf-8", b"Synthetic cannabis catalogue")

    async def run():
        for _ in range(3):
            assert await process_one(db_session_factory, fetcher=fake_fetch)
        assert not await process_one(db_session_factory, fetcher=fake_fetch)

    asyncio.run(run())
    assert set(seen) == {root, catalog, blocked} and len(seen) == 3
    page_list = client.get(pages, headers=HEADERS)
    assert page_list.status_code == 200, page_list.text
    rows = {row["url"]: row for row in page_list.json()["items"]}
    assert rows[blocked]["error_code"] == "BROWSER_CHECK_REQUIRED"
    assert rows[catalog]["status"] == "COMPLETED"
    assert client.delete(f'{pages}/{rows[root]["id"]}', headers=HEADERS).status_code == 204
    assert client.get(pages, headers=HEADERS).json()["total"] == 2

    report = client.post("/api/v1/reports", headers=HEADERS, json={
        "source_id": observed["source_id"], "period_start": begin.isoformat(),
        "period_end": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(),
    })
    assert report.status_code == 201, report.text
    report_path = "/api/v1/reports/" + report.json()["id"]
    preview = client.get(report_path + "/publication-preview", headers=HEADERS).json()
    assert preview["content"]["totals"]["observations"] == 3
    pub = client.post(report_path + "/publication", headers=HEADERS, json={"expected_digest": preview["digest"]})
    assert pub.status_code == 201, pub.text
    public = client.get("/api/public/v1/reports/" + pub.json()["publication_id"])
    assert public.status_code == 200 and public.json()["content"]["totals"]["alerts"] >= 1
    assert catalog not in public.text and "CAPTURE_RAW_SENTINEL" not in public.text
