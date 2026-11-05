"""M4-A: synthetic, database-only observation search and provenance coverage."""
from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import select
from app.models import CrawlJob, OnionSource, SourceObservation
from tests.test_manual_queue_rc2 import LEGACY, create_role


def seed(factory):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    with factory() as db:
        one = OnionSource(canonical_url='http://synthetic-one.onion/', name='One',
                          category='FORUM', authorization_note='Synthetic authorized fixture')
        two = OnionSource(canonical_url='http://synthetic-two.onion/', name='Two',
                          category='MARKET', authorization_note='Synthetic authorized fixture')
        db.add_all([one,two]); db.flush()
        created = []
        for source,title,description,sha,status,at in [
            (one,'Reference Alpha','A short description 50%','a'*64,'FIRST_SEEN',now-timedelta(days=2)),
            (one,'Reference Beta','Updated metadata and title','b'*64,'MODIFIED',now-timedelta(days=1)),
            (one,'Reference Beta','Updated metadata and title','b'*64,'UNCHANGED',now),
            (two,'Sensitive_OTHER','Other category record','c'*64,'FIRST_SEEN',now),
        ]:
            job = CrawlJob(source_id=source.id, status='COMPLETED', created_at=at,
                           started_at=at, finished_at=at)
            db.add(job); db.flush()
            obs = SourceObservation(job_id=job.id,source_id=source.id, title=title,
                description=description, text_sha256=sha,text_length=len(description),
                http_status=200,content_type='text/html',response_bytes=300,
                change_status=status,created_at=at)
            db.add(obs); db.flush(); created.append((source.id,obs.id))
        db.commit()
    return now,created


def get(client, path, headers=LEGACY):
    return client.get('/api/v1/observations'+path,headers=headers)


def test_search_auth_filters_sort_and_page(client,db_session_factory):
    now,rows=seed(db_session_factory)
    assert get(client,'/search',headers={}).status_code == 401
    viewer=create_role(db_session_factory,'VIEWER')
    res=get(client,'/search?limit=2',viewer)
    assert res.status_code==200 and res.json()['total']==4
    assert len(res.json()['items'])==2
    assert 'source_name' in res.json()['items'][0]
    page=get(client,'/search?limit=2&offset=2',viewer).json()
    assert len({x['id'] for x in page['items']} & {x['id'] for x in res.json()['items']})==0
    source_id=rows[0][0]
    assert get(client,f'/search?source_id={source_id}',viewer).json()['total']==3
    assert get(client,'/search?category=MARKET',viewer).json()['total']==1
    assert get(client,'/search?change_status=MODIFIED',viewer).json()['total']==1
    assert get(client,'/search?sha256='+'b'*64,viewer).json()['total']==2
    assert get(client,'/search?q=reference',viewer).json()['total']==3
    assert get(client,'/search?q=updated',viewer).json()['total']==2
    assert get(client,'/search?q=50%25',viewer).json()['total']==1
    assert get(client,'/search?q=_OTHER',viewer).json()['total']==1
    assert get(client,'/search?since='+ (now-timedelta(hours=3)).isoformat().replace('+00:00','Z'),viewer).json()['total']==2
    assert get(client,'/search?until='+ (now-timedelta(days=1,hours=12)).isoformat().replace('+00:00','Z'),viewer).json()['total']==1


def test_input_validation_and_no_wildcard_bypass(client,db_session_factory):
    seed(db_session_factory)
    for qs in ('q=%20%20%20','q=%25%25','q=x','q='+('x'*121),
               'change_status=INVALID','limit=101','offset=10001',
               'sha256='+('x'*64),'since=2026-10-01T12:00:00',
               'since=2026-10-03T00:00:00Z&until=2026-10-02T00:00:00Z'):
        res=get(client,'/search?'+qs)
        assert res.status_code == 422, (qs,res.text)
    assert get(client,'/search?q=%25%25a').json()['total']==0


def test_provenance_order_same_source_and_limited_comparison(client,db_session_factory):
    _, rows=seed(db_session_factory)
    first,middle,last=[str(row[1]) for row in rows[:3]]
    r=get(client,f'/{middle}/provenance')
    assert r.status_code==200
    info=r.json()
    assert info['previous_observation_id']==first
    assert info['hash_changed'] is True
    assert info['metadata_changes']['title']=={'before':'Reference Alpha','after':'Reference Beta'}
    assert info['job']['status']=='COMPLETED'
    assert 'body' not in r.text and 'lease_token' not in r.text
    assert get(client,f'/{last}/provenance').json()['hash_changed'] is False
    assert get(client,f'/{first}/provenance').json()['hash_changed'] is None
    assert get(client,f'/{uuid.uuid4()}/provenance').status_code==404


def test_readonly_retention_preview_admin_only(client,db_session_factory):
    seed(db_session_factory)
    viewer=create_role(db_session_factory,'VIEWER')
    assert get(client,'/retention/preview',viewer).status_code == 403
    assert get(client,'/retention/preview?older_than_days=1').status_code == 422
    ret=get(client,'/retention/preview?older_than_days=30')
    assert ret.status_code==200 and ret.json()['observation_count']==0
    assert ret.json()['deletion_enabled'] is False and ret.json()['dry_run'] is True
    with db_session_factory() as db:
        assert len(db.scalars(select(SourceObservation)).all())==4
