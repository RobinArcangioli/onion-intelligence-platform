"""Full fictional chain: actual queue, worker, extraction, CTI, alerts and reports."""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.main import app
from app.models import Alert, AuditLog, CrawlJob, Report, SourceObservation
from app.schemas.publication import PublicIncidentDraft
from scripts.leak_simulation import OfflineScenarioTransport, prepare_sources, run_chain
from app.collector.transport import CollectError

ADMIN={'X-API-Key':'local-test-only-api-key-strong-and-unique'}


def test_two_observations_trigger_real_alerts_and_reviewed_public_reports(client,db_session_factory):
    prepare_sources(db_session_factory)
    result=asyncio.run(run_chain(app,db_session_factory,ADMIN['X-API-Key']))
    assert len(result)==2
    assert client.get('/api/public/v1/reports').json()['total']==0
    with db_session_factory() as db:
        assert len(list(db.scalars(select(CrawlJob).where(CrawlJob.status=='COMPLETED'))))==2
        observations=list(db.scalars(select(SourceObservation)))
        alerts=list(db.scalars(select(Alert)))
        reports=list(db.scalars(select(Report)))
        assert len(observations)==len(alerts)==len(reports)==2
        assert {a.signal_code for a in alerts}=={'DATA_LEAK_CLAIM'}
        assert {a.verification_status for a in alerts}=={'OBSERVED_CLAIM'}
        for row in reports:
            assert row.snapshot['totals']['observations']==1
            assert row.snapshot['totals']['alerts']==1
            assert row.snapshot['records']['observations'][0]['source_id']==str(row.source_id)
            assert 'SIMULATION_INTERNAL_CONTEXT' not in str(row.snapshot)
    for scenario in result:
        base=f'/api/v1/reports/{scenario["report_id"]}'
        preview=client.get(base+'/publication-preview',headers=ADMIN).json()
        assert preview['content']['schema_version']=='PUBLIC_REVIEW_V2'
        assert preview['content']['incident']['company_name']==scenario['company_name']
        assert preview['content']['incident']['simulation'] is True
        assert client.post(base+'/publication',headers=ADMIN,json={'expected_digest':preview['digest']}).status_code==409
        incident=preview['content']['incident']
        incident['summary']+=' Relecture manuelle effectuée dans le cadre de cet exercice fictif.'
        # A changed draft cannot be silently substituted after preview.
        assert client.post(base+'/publication',headers=ADMIN,json={'expected_digest':preview['digest'],
            'incident':incident,'review_confirmed':True}).status_code==409
        edited=client.post(base+'/publication-preview',headers=ADMIN,json={'incident':incident})
        assert edited.status_code==200
        published=client.post(base+'/publication',headers=ADMIN,json={'expected_digest':edited.json()['digest'],
            'incident':incident,'review_confirmed':True})
        assert published.status_code==201,published.text
        public=client.get('/api/public/v1/reports/'+published.json()['publication_id'])
        assert public.status_code==200
        assert public.json()['content']['incident']==incident
        for hidden in ['SIMULATION_INTERNAL_CONTEXT','.onion','observation_id','source_id','demo_admin']:
            assert hidden not in public.text
    assert client.get('/api/public/v1/reports').json()['total']==2
    with db_session_factory() as db:
        logs=list(db.scalars(select(AuditLog).where(AuditLog.action=='report.publish')))
        assert len(logs)==2
        assert all('"review_confirmed": true' in log.details for log in logs)


def incident_fixture():
    return dict(title='Simulation de fuite fictive',company_name='Entreprise fictive',sector='Exercice',
                summary='Une revendication entièrement fictive est examinée pour cet exercice.',
                data_categories=['CUSTOMER_RECORDS'],affected_records=42,
                detected_at=datetime.now(timezone.utc).isoformat(),
                recommendations='Effectuer une vérification documentaire fictive.',simulation=True)


@pytest.mark.parametrize('field,value',[('summary','Consulter http://private.onion/ pour les données.'),
    ('company_name','operator@example.invalid'),('summary','<script>unsafe</script>'),
    ('recommendations','token=privatevalue'),('affected_records','42'),
    ('detected_at','2026-11-05T12:00:00'),('data_categories',['RAW_CREDENTIALS']),
    ('summary',''),('simulation','false')])
def test_public_draft_rejects_unsafe_or_ambiguous_fields(field,value):
    payload=incident_fixture();payload[field]=value
    with pytest.raises(ValidationError):PublicIncidentDraft.model_validate(payload)


def test_simulation_transport_has_no_network_fallback():
    fetcher=OfflineScenarioTransport()
    with pytest.raises(CollectError):asyncio.run(fetcher('https://external.invalid/'))
    assert fetcher.calls==[]
