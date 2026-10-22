"""Only synthetic pages and ephemeral content. No network / real Onion access."""
import asyncio
import uuid
import pytest
from sqlalchemy import func, select
from app.classifiers.rules import classify_document, CATEGORY_RULES, RULESET_VERSION, taxonomy
from app.collector.runner import collect_one, NotAuthorizedError
from app.collector.transport import Fetched
from app.models import (AuditLog, ClassificationResult, DiscoveredOnion,
                        KeywordMatch, OnionSource, SourceObservation, ThreatIndicator)
from tests.test_tor_collection import API_HEADERS, enabled, onion


@pytest.mark.parametrize('category,phrase', [(name, terms[0][1]) for name,terms in CATEGORY_RULES.items()])
def test_taxonomy_rules_are_explainable_and_safe(category, phrase):
    result = classify_document('An example: ' + phrase)
    assert category in [x.category for x in result.categories]
    finding = next(x for x in result.categories if x.category == category)
    assert finding.confidence <= 75
    assert all(' ' not in code for code in finding.evidence_codes)
    assert finding.review_status == ('REVIEW_REQUIRED' if category in ('EXTREMIST_PROPAGANDA','SUSPECTED_CHILD_EXPLOITATION') else 'AUTO_SUGGESTED')
    assert phrase not in str(finding.evidence_codes)


def test_no_evidence_no_labels():
    finding = classify_document('The weather is clear today.')
    assert finding.categories == () and finding.indicators == () and finding.quarantine is False


def test_public_cve_deduplicated_and_bounded():
    finding = classify_document('CVE-2025-12345 cve-2025-12345 CVE-1999-1234 CVE-2020-12345X')
    assert len(finding.indicators) == 1
    assert finding.indicators[0].public_reference == 'CVE-2025-12345'
    assert finding.indicators[0].verification_status == 'OBSERVED_REFERENCE'
    items = classify_document(' '.join(f'CVE-2024-{10000+i}' for i in range(50))).indicators
    assert len(items) == 20


def test_claim_is_not_confirmed():
    result = classify_document('ransomware leak and stolen database initial access for sale')
    assert {i.indicator_type for i in result.indicators} == {'RANSOMWARE_CLAIM','DATA_LEAK_CLAIM','ACCESS_SALE_CLAIM'}
    assert all(i.verification_status == 'OBSERVED_CLAIM' for i in result.indicators)
    assert all(i.public_reference == '' for i in result.indicators)
    assert all(i.confidence < 80 for i in result.indicators)


def test_sensitive_quarantine_only_minimal_indicator():
    result = classify_document('news article child sexual abuse material CVE-2025-12345 stolen database')
    assert result.quarantine
    assert len(result.categories) == 1
    assert result.categories[0].category == 'SUSPECTED_CHILD_EXPLOITATION'
    assert result.indicators == ()


def test_taxonomy_public_codes_not_raw_phrases():
    serialized = str(taxonomy())
    assert RULESET_VERSION in serialized
    assert 'child sexual abuse material' not in serialized
    assert len(taxonomy()) == len(CATEGORY_RULES)


def test_cti_requires_key(client):
    for path in ['/api/v1/cti/taxonomy','/api/v1/cti/classifications',
                 '/api/v1/cti/indicators', '/api/v1/cti/correlations']:
        assert client.get(path).status_code == 401


def test_cti_end_to_end_review_and_cooccurrence(client, valid_onion_url, db_session_factory):
    sid = enabled(client, valid_onion_url)
    watch = client.post('/api/v1/watchlists',headers=API_HEADERS,json={'name':'Demo entity'}).json()
    rule = client.post(f'/api/v1/watchlists/{watch["id"]}/rules',headers=API_HEADERS,
                       json={'phrase':'Demo Corporation','weight':20})
    assert rule.status_code == 201
    async def fetcher(url):
        return Fetched(200,'text/html','utf-8', b'<html><title>News article</title><main>Demo Corporation mentioned. '
                       b'An unverified stolen database notice references CVE-2025-98765 and ransomware leak.</main></html>')
    job_id, status = asyncio.run(collect_one(uuid.UUID(sid), db_session_factory, fetcher=fetcher))
    assert status == 'COMPLETED'
    cats = client.get('/api/v1/cti/classifications',headers=API_HEADERS).json()
    assert cats['total'] >= 2
    assert all(x['confidence'] <= 75 for x in cats['items'])
    assert 'stolen database' not in str(cats)
    indicators = client.get('/api/v1/cti/indicators',headers=API_HEADERS).json()
    assert {x['indicator_type'] for x in indicators['items']} >= {'DATA_LEAK_CLAIM','PUBLIC_CVE_REFERENCE','RANSOMWARE_CLAIM'}
    assert {x['verification_status'] for x in indicators['items']} == {'OBSERVED_CLAIM','OBSERVED_REFERENCE'}
    correlations = client.get('/api/v1/cti/correlations',headers=API_HEADERS).json()
    assert correlations['total'] == indicators['total']
    assert all(x['occurrences'] >= 1 for x in correlations['items'])
    assert watch['id'] in {x['watchlist_id'] for x in correlations['items']}
    one_id = cats['items'][0]['id']
    assert client.get('/api/v1/cti/classifications?category=NEWS',headers=API_HEADERS).json()['total'] == 1
    assert client.get('/api/v1/cti/classifications?limit=0',headers=API_HEADERS).status_code == 422
    assert client.post(f'/api/v1/cti/classifications/{one_id}/review',headers=API_HEADERS,
                       json={'decision':'ACCEPTED','reason':'Manual check'}).json()['review_status'] == 'ACCEPTED'
    assert client.post(f'/api/v1/cti/classifications/{one_id}/review',headers=API_HEADERS,
                       json={'decision':'REJECTED','reason':'Manual check'}).status_code == 409
    assert client.get(f'/api/v1/cti/classifications/{one_id}',headers=API_HEADERS).status_code == 200
    assert client.get('/api/v1/cti/classifications?review_status=ACCEPTED',headers=API_HEADERS).json()['total'] == 1
    assert client.get('/api/v1/cti/indicators?indicator_type=PUBLIC_CVE_REFERENCE',headers=API_HEADERS).json()['total'] == 1
    with db_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=='classification.review')) == 1
        src=db.get(OnionSource,uuid.UUID(sid))
        assert src.collection_enabled  # reviews never alter permissions
        obs=db.scalar(select(SourceObservation).where(SourceObservation.job_id==job_id))
        assert obs.relevance_score == 20  # independent relevance score
        assert not hasattr(obs,'raw_html')


def test_sensitive_collection_is_quarantined_and_does_not_store_candidates(client, valid_onion_url, db_session_factory):
    sid = enabled(client, valid_onion_url)
    target=onion(52)
    async def fetcher(url):
        return Fetched(200,'text/plain','utf-8',
                       ('child sexual abuse material CVE-2025-12345 ' + target).encode())
    jid, status = asyncio.run(collect_one(uuid.UUID(sid), db_session_factory, fetcher=fetcher))
    assert status == 'COMPLETED'
    with db_session_factory() as db:
        source=db.get(OnionSource, uuid.UUID(sid))
        assert source.collection_enabled is False
        obs=db.scalar(select(SourceObservation).where(SourceObservation.job_id==jid))
        assert obs.title == '' and obs.description == ''
        assert obs.discovered_links == 0 and obs.keyword_hits == 0
        assert db.scalar(select(func.count()).select_from(DiscoveredOnion)) == 0
        assert db.scalar(select(func.count()).select_from(KeywordMatch)) == 0
        assert db.scalar(select(func.count()).select_from(ThreatIndicator)) == 0
        classification=db.scalar(select(ClassificationResult))
        assert classification.review_status == 'REVIEW_REQUIRED'
        assert classification.category == 'SUSPECTED_CHILD_EXPLOITATION'
        assert db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action=='collection.sensitive_quarantine')) == 1
    with pytest.raises(NotAuthorizedError):
        asyncio.run(collect_one(uuid.UUID(sid), db_session_factory, fetcher=fetcher))
    cats=client.get('/api/v1/cti/classifications',headers=API_HEADERS).json()
    assert cats['total'] == 1
    assert 'child sexual abuse material' not in str(cats)


def test_review_validation(client, valid_onion_url, db_session_factory):
    sid=enabled(client,valid_onion_url)
    async def fetcher(url):
        return Fetched(200,'text/plain','utf-8',b'news article')
    asyncio.run(collect_one(uuid.UUID(sid),db_session_factory,fetcher=fetcher))
    row=client.get('/api/v1/cti/classifications',headers=API_HEADERS).json()['items'][0]
    endpoint=f'/api/v1/cti/classifications/{row["id"]}/review'
    assert client.post(endpoint,headers=API_HEADERS,json={'decision':'CONFIRMED','reason':'Manual check'}).status_code==422
    assert client.post(endpoint,headers=API_HEADERS,json={'decision':'REJECTED','reason':'ok'}).status_code==422
    assert client.post(endpoint,headers=API_HEADERS,json={'decision':'REJECTED','reason':'Manual check', 'secret':'x'}).status_code==422
    assert client.post(endpoint,headers=API_HEADERS,json={'decision':'REJECTED','reason':'Manual check'}).status_code==200
    assert client.get('/api/v1/cti/classifications?review_status=REJECTED',headers=API_HEADERS).json()['total'] == 1


def test_empty_cti_lists_and_unknown_ids(client):
    for path in ['/api/v1/cti/indicators','/api/v1/cti/classifications','/api/v1/cti/correlations']:
        assert client.get(path,headers=API_HEADERS).json()['total'] == 0
    random_id=uuid.uuid4()
    assert client.get(f'/api/v1/cti/indicators/{random_id}',headers=API_HEADERS).status_code==404
    assert client.get(f'/api/v1/cti/classifications/{random_id}',headers=API_HEADERS).status_code==404
    assert client.post(f'/api/v1/cti/classifications/{random_id}/review',headers=API_HEADERS,
                       json={'decision':'ACCEPTED'}).status_code == 404


def test_quarantine_cannot_be_hidden_by_max_category_cap():
    from app.classifiers.rules import MAX_CLASSIFICATIONS
    long_text = ' '.join(rule_set[0][1] for _, rule_set in CATEGORY_RULES.items())
    assert len(CATEGORY_RULES) > MAX_CLASSIFICATIONS
    result = classify_document(long_text)
    assert result.quarantine
    assert result.categories[0].category == 'SUSPECTED_CHILD_EXPLOITATION'
    assert result.indicators == ()
