"""Two fictional leak scenarios exercised through the real application pipeline.

Only fake HTML transport is substituted. Never accepts a PostgreSQL database,
never starts Tor, and never falls back to a network request.
"""
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import httpx
from sqlalchemy import select

from app.collector.transport import CollectError, Fetched
from app.collector.worker import process_one
from app.models import Alert, CrawlJob, OnionSource, SourceObservation

SCENARIOS = (
    dict(code='ALPHA-01', company_name='Entreprise fictive ALPHA-01', sector='Commerce fictif',
         affected_records=2500, data_categories=['CUSTOMER_RECORDS', 'CONTACT_DETAILS'],
         phrase='leaked customer records',
         summary='Une publication de simulation prétend proposer 2 500 fiches clients de l’entreprise fictive ALPHA-01. Les catégories annoncées sont des coordonnées professionnelles fictives et des références clients inventées. Aucun jeu de données réel n’est présent.',
         recommendations='Dans cet exercice, vérifier l’origine de la publication et prévenir le responsable de sécurité fictif. Ne télécharger aucun échantillon.'),
    dict(code='BETA-02', company_name='Entreprise fictive BETA-02', sector='Logistique fictive',
         affected_records=750, data_categories=['EMPLOYEE_RECORDS', 'INTERNAL_DOCUMENTS'],
         phrase='stolen database',
         summary='Une seconde publication de simulation revendique une base de 750 dossiers fictifs liés à l’entreprise fictive BETA-02. Elle mentionne des documents internes et des références de collaborateurs entièrement inventés. La revendication n’est pas une preuve de compromission.',
         recommendations='Dans cet exercice, faire examiner le signal par l’équipe de sécurité fictive, contrôler les accès et préparer une communication vérifiée.'),
)


def guard_factory(factory):
    engine = factory.kw['bind']
    if engine.dialect.name != 'sqlite':
        raise ValueError('Simulation requires disposable synthetic SQLite')
    database = engine.url.database
    if database not in (None, '', ':memory:') and not Path(database).parent.name.startswith('oip-visitor-demo-'):
        raise ValueError('Refusing a non-demo database')


def fixture_url(index):
    key=bytes([index+1])*32
    checksum=hashlib.sha3_256(b'.onion checksum'+key+b'\x03').digest()[:2]
    return 'http://'+base64.b32encode(key+checksum+b'\x03').decode().lower().rstrip('=')+'.onion/'


def prepare_sources(factory):
    guard_factory(factory)
    with factory() as db:
        for index, scenario in enumerate(SCENARIOS):
            db.add(OnionSource(canonical_url=fixture_url(index),
                name='Veille simulée '+scenario['code'],
                authorization_note='Synthetic local simulation only; no real service is contacted',
                collection_enabled=True))
        db.commit()


class OfflineScenarioTransport:
    def __init__(self):
        self.calls=[]
        self.pages={fixture_url(i): (f'<html><head><title>Simulation {s["code"]}</title></head>'
            f'<body><h1>{s["company_name"]} — FICTIONAL EXERCISE</h1>'
            f'<p>{s["phrase"]}. All records are fictional. No real breach.</p>'
            f'<p>SIMULATION_INTERNAL_CONTEXT_{s["code"]}</p></body></html>').encode()
            for i,s in enumerate(SCENARIOS)}

    async def __call__(self, url):
        if url not in self.pages:
            raise CollectError('SIMULATION_SOURCE_NOT_ALLOWED')
        self.calls.append(url)
        return Fetched(status=200, content_type='text/html', encoding='utf-8', body=self.pages[url])


async def run_chain(app, factory, fixture_token):
    guard_factory(factory)
    fetcher=OfflineScenarioTransport()
    outcomes=[]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                base_url='http://synthetic.invalid',
                                headers={'X-API-Key':fixture_token}) as client:
        for index, scenario in enumerate(SCENARIOS):
            with factory() as db:
                source=db.scalar(select(OnionSource).where(OnionSource.canonical_url==fixture_url(index)))
                if source is None:
                    raise RuntimeError('Simulation source not prepared')
                source_id=source.id
            start=datetime.now(timezone.utc)-timedelta(minutes=1)
            queued=await client.post(f'/api/v1/sources/{source_id}/collection/run',
                                     json={'reason':'Explicit synthetic simulation'})
            if queued.status_code!=202:
                raise RuntimeError('Synthetic job admission failed')
            job_id=queued.json()['id']
            if not await process_one(factory,fetcher=fetcher):
                raise RuntimeError('Synthetic worker did not claim a job')
            with factory() as db:
                job=db.scalar(select(CrawlJob).where(CrawlJob.id==UUID(job_id)))
                observation=db.scalar(select(SourceObservation).where(SourceObservation.job_id==job.id))
                alert=db.scalar(select(Alert).where(Alert.observation_id==observation.id,
                    Alert.signal_code=='DATA_LEAK_CLAIM')) if observation else None
                if job.status!='COMPLETED' or observation is None or alert is None:
                    raise RuntimeError('Real classification or alert generation failed')
                observation_id,alert_id=observation.id,alert.id
            draft={key:scenario[key] for key in ('company_name','sector','summary','data_categories',
                                                'affected_records','recommendations')}
            draft.update(title='Simulation — fuite suspectée chez '+scenario['company_name'],
                         detected_at=datetime.now(timezone.utc).isoformat(),simulation=True)
            report=await client.post('/api/v1/reports',json={
                'source_id':str(source_id), 'period_start':start.isoformat(),
                'period_end':(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat(),
                'max_rows_per_type':100, 'public_draft':draft})
            if report.status_code!=201:
                raise RuntimeError('Synthetic report generation failed')
            outcomes.append(dict(code=scenario['code'], company_name=scenario['company_name'],
                job_id=job_id, observation_id=str(observation_id),alert_id=str(alert_id),
                report_id=report.json()['id'],status='READY_FOR_ADMIN_REVIEW'))
    if len(fetcher.calls)!=2:
        raise RuntimeError('Unexpected synthetic fetch count')
    return outcomes
