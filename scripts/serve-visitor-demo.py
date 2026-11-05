#!/usr/bin/env python3
"""Disposable visitor acceptance server: loopback, temporary synthetic data only.

Never loads a database DSN or operator credential from the environment.
The fixed CI token below is only valid in this synthetic temporary application.
"""
import base64
import hashlib
import os
import tempfile
import atexit
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

# Do this before importing any application component.
for key in list(os.environ):
    if key.startswith('OIP_'):
        del os.environ[key]

from fastapi.staticfiles import StaticFiles
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import uvicorn

from app.main import app
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_session
from app.models import CrawlJob, OnionSource, Operator, OperatorToken, Report, ReportPublication, SourceObservation
from app.public_view.projections import project_report
from app.security.api_key import fingerprint

ROOT=Path(__file__).resolve().parents[1]
FIXTURE_TOKEN='oip_CI_SYNTHETIC_NOT_A_REAL_OPERATOR_CREDENTIAL'
sandbox=tempfile.TemporaryDirectory(prefix='oip-visitor-demo-')
engine=create_engine('sqlite+pysqlite:///'+str(Path(sandbox.name)/'synthetic.db'),connect_args={'check_same_thread':False})
atexit.register(lambda: (engine.dispose(), sandbox.cleanup()))
Base.metadata.create_all(engine)
factory=sessionmaker(bind=engine,expire_on_commit=False)
now=datetime.now(timezone.utc)
key=bytes(range(32)); checksum=hashlib.sha3_256(b'.onion checksum'+key+b'\x03').digest()[:2]
host=base64.b32encode(key+checksum+b'\x03').decode().lower().rstrip('=')+'.onion'
with factory() as db:
    operator=Operator(username='demo_admin',role='ADMIN');db.add(operator);db.flush()
    db.add(OperatorToken(operator_id=operator.id,token_hash=fingerprint(FIXTURE_TOKEN),expires_at=now+timedelta(hours=2)))
    source=OnionSource(name='Source de démonstration',canonical_url='http://'+host+'/',authorization_note='Synthetic local fixture')
    db.add(source);db.flush()
    job=CrawlJob(source_id=source.id,status='COMPLETED',finished_at=now,error_code='INTERNAL_PRIVATE_SENTINEL')
    db.add(job);db.flush()
    db.add(SourceObservation(source_id=source.id,job_id=job.id,http_status=200,content_type='text/plain',response_bytes=12500,text_length=512,text_sha256='c'*64,title='INTERNAL_PRIVATE_SENTINEL'))
    for index in (1,2):
        report=Report(id=UUID(f'11111111-1111-4111-8111-{index:012d}'),period_start=now-timedelta(days=1),period_end=now,
                      snapshot={'totals':dict(observations=index,discoveries=0,classifications=0,indicators=0,alerts=0),
                                'records':{'private':'INTERNAL_PRIVATE_SENTINEL'}})
        db.add(report);db.flush()
        if index==2:
            db.add(ReportPublication(report_id=report.id,payload=project_report(report).model_dump(mode='json'),published_by='demo_admin'))
    db.commit()


def session():
    with factory() as db:
        yield db


def settings():
    return Settings(database_url='sqlite+pysqlite://',api_key=SecretStr('synthetic-demo-only-not-an-operational-key'),
                    legacy_api_key_enabled=False,manual_collection_enabled=False)

app.dependency_overrides[get_session]=session
app.dependency_overrides[get_settings]=settings
app.mount('/',StaticFiles(directory=ROOT/'frontend/dist',html=True),name='synthetic-frontend')
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8010)
    args=parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Use an unprivileged local port')
    uvicorn.run(app,host='127.0.0.1',port=args.port,access_log=False)
