"""All tests use synthetic text, never Tor or a real .onion source."""
import asyncio
import uuid

from sqlalchemy import func, select

from app.analyzers.keywords import RuleSpec, analyze_text
from app.collector.extract import extract_html
from app.collector.runner import collect_one
from app.collector.transport import Fetched
from app.models import DiscoveredOnion, KeywordMatch, OnionSource, SourceObservation
from tests.test_tor_collection import API_HEADERS, enabled, onion


def test_keyword_scoring_and_word_boundaries():
    rules = [RuleSpec(uuid.uuid4(), 'Acme Corp', 12), RuleSpec(uuid.uuid4(), 'cat', 5),
             RuleSpec(uuid.uuid4(), 'incident', 15)]
    result = analyze_text('ACME CORP cat catalog. Acme Corp incident incident incident incident', rules)
    assert result.score == 12*2 + 5 + 15*3
    assert [(h.occurrences, h.contribution) for h in result.hits] == [(2,24),(1,5),(4,45)]


def test_score_bounded_and_regex_literal():
    result = analyze_text('a+b a+b ' * 100, [RuleSpec(uuid.uuid4(), 'a+b', 30)]*4)
    assert result.score == 100
    assert all(hit.occurrences == 20 for hit in result.hits)
    assert analyze_text('anything', [RuleSpec(uuid.uuid4(), '.*', 30)]).score == 0


def test_transient_extraction_html_and_plain(valid_onion_url):
    target = onion(100)
    html = (f'<script>{onion(101)}</script><main>Example <a href="{target}">notice</a>'
            f' {target[:-1]} incident</main><nav>{onion(102)}</nav>').encode()
    ext = extract_html(html, 'utf8', content_type='text/html', page_url=valid_onion_url)
    assert ext.candidates[0].evidence_kind == 'BOTH'
    assert ext.onion_roots == (target,)
    assert 'Example' in ext.transient_text
    assert onion(101) not in ext.transient_text
    plain = extract_html(('Read ' + target + ' now').encode(), 'utf-8', content_type='text/plain', page_url=valid_onion_url)
    assert plain.candidates[0].evidence_kind == 'TEXT'
    assert plain.onion_roots == (target,)


def test_invalid_onion_mentions_and_candidate_cap(valid_onion_url):
    invalid = 'a'*56 + '.onion'
    ext = extract_html(f'<main>{invalid} <a href="http://{invalid}/">x</a></main>'.encode(), 'utf-8',
                       content_type='text/html', page_url=valid_onion_url)
    assert ext.onion_roots == ()
    payload = ' '.join(onion(x) for x in range(70))
    ext = extract_html(payload.encode(), 'utf-8', content_type='text/plain', page_url=valid_onion_url)
    assert len(ext.onion_roots) == 50


def test_watchlists_and_rules_api(client):
    assert client.get('/api/v1/watchlists').status_code == 401
    assert client.post('/api/v1/watchlists', json={'name':'T'},headers=API_HEADERS).status_code == 422
    response = client.post('/api/v1/watchlists', json={'name':'Brand watch'}, headers=API_HEADERS)
    assert response.status_code == 201
    wid = response.json()['id']
    assert client.post('/api/v1/watchlists', json={'name':'Brand watch'}, headers=API_HEADERS).status_code == 409
    rule = client.post(f'/api/v1/watchlists/{wid}/rules', json={'phrase':'ACME Corp','weight':20},headers=API_HEADERS)
    assert rule.status_code == 201
    rid=rule.json()['id']
    assert client.post(f'/api/v1/watchlists/{wid}/rules', json={'phrase':'acme  corp'},headers=API_HEADERS).status_code == 409
    assert client.post(f'/api/v1/watchlists/{wid}/rules', json={'phrase':'ab','weight':31},headers=API_HEADERS).status_code == 422
    assert client.get(f'/api/v1/watchlists/{wid}/rules',headers=API_HEADERS).json()['total'] == 1
    assert client.patch(f'/api/v1/watchlist-rules/{rid}',json={'is_active':False,'reason':'Manual check'},headers=API_HEADERS).json()['is_active'] is False
    assert client.patch(f'/api/v1/watchlists/{wid}',json={'is_active':False,'reason':'Manual check'},headers=API_HEADERS).json()['is_active'] is False


def test_collection_analysis_and_review_no_auto_approval(client, valid_onion_url, db_session_factory):
    sid=enabled(client,valid_onion_url)
    wid=client.post('/api/v1/watchlists',headers=API_HEADERS,json={'name':'Test entities'}).json()['id']
    response=client.post(f'/api/v1/watchlists/{wid}/rules',headers=API_HEADERS,json={'phrase':'Example Org','weight':18})
    assert response.status_code == 201, response.text
    target=onion(88)
    async def fetcher(url):
        assert url == valid_onion_url
        return Fetched(200,'text/html','utf-8',f'<title>Notice</title><p>Example Org reported Example Org</p><a href="{target}">Link</a>'.encode())
    jid,state=asyncio.run(collect_one(uuid.UUID(sid),db_session_factory,fetcher=fetcher))
    assert state == 'COMPLETED'
    with db_session_factory() as db:
        obs=db.scalar(select(SourceObservation).where(SourceObservation.job_id==jid))
        assert (obs.relevance_score,obs.keyword_hits,obs.discovered_links)==(36,2,1)
        assert not hasattr(obs,'transient_text') and not hasattr(obs,'body')
        match=db.scalar(select(KeywordMatch))
        assert match.occurrences==2
        cid=db.scalar(select(DiscoveredOnion)).id
        oid=obs.id
    analysis=client.get(f'/api/v1/collection/observations/{oid}/analysis',headers=API_HEADERS)
    assert analysis.status_code==200
    assert analysis.json()['matches'][0]['contribution']==36
    assert 'reported Example Org' not in str(analysis.json())
    assert client.get('/api/v1/collection/discoveries?status=PENDING',headers=API_HEADERS).json()['total']==1
    reviewed=client.post(f'/api/v1/collection/discoveries/{cid}/review',headers=API_HEADERS,json={'decision':'APPROVED','reason':'Manual check'})
    assert reviewed.status_code==200 and reviewed.json()['status']=='APPROVED'
    assert client.post(f'/api/v1/collection/discoveries/{cid}/review',headers=API_HEADERS,json={'decision':'REJECTED','reason':'Manual check'}).status_code==409
    with db_session_factory() as db:
        assert db.scalar(select(func.count()).select_from(OnionSource))==1
    asyncio.run(collect_one(uuid.UUID(sid),db_session_factory,fetcher=fetcher))
    with db_session_factory() as db:
        assert db.get(DiscoveredOnion,cid).status=='APPROVED'
        assert db.scalar(select(func.count()).select_from(DiscoveredOnion))==1


def test_rule_deactivation_works_next_job(client, valid_onion_url, db_session_factory):
    sid=enabled(client, valid_onion_url)
    wid=client.post('/api/v1/watchlists',headers=API_HEADERS,json={'name':'Temporary'}).json()['id']
    rid=client.post(f'/api/v1/watchlists/{wid}/rules',headers=API_HEADERS,json={'phrase':'Company X','weight':11}).json()['id']
    async def fake(_): return Fetched(200,'text/plain','utf-8',b'Company X')
    asyncio.run(collect_one(uuid.UUID(sid),db_session_factory,fetcher=fake))
    client.patch(f'/api/v1/watchlist-rules/{rid}',headers=API_HEADERS,json={'is_active':False,'reason':'Manual check'})
    asyncio.run(collect_one(uuid.UUID(sid),db_session_factory,fetcher=fake))
    with db_session_factory() as db:
        obs=db.scalars(select(SourceObservation)).all()
        assert sorted(x.relevance_score for x in obs)==[0,11]


def test_candidate_limit_with_mix_of_href_and_mentions(valid_onion_url):
    hrefs = ''.join(f'<a href="{onion(i)}">a</a>' for i in range(1, 51))
    body = f'<main>{hrefs} {onion(70)}</main>'
    extracted = extract_html(body.encode(), 'utf-8', content_type='text/html', page_url=valid_onion_url)
    assert len(extracted.onion_roots) == 50
    assert onion(70) not in extracted.onion_roots


def test_change_tracking_by_hash(client, valid_onion_url, db_session_factory):
    sid = enabled(client, valid_onion_url)
    responses = [b'<p>State A</p>', b'<p>State A</p>', b'<p>State B</p>']
    for payload in responses:
        async def fake(_): return Fetched(200, 'text/html', 'utf-8', payload)
        asyncio.run(collect_one(uuid.UUID(sid), db_session_factory, fetcher=fake))
    with db_session_factory() as db:
        got = [x.change_status for x in db.scalars(select(SourceObservation)).all()]
        assert sorted(got) == ['FIRST_SEEN', 'MODIFIED', 'UNCHANGED']
