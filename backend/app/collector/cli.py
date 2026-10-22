"""python -m app.collector.cli SOURCE_UUID (uniquement conteneur collector)."""
import argparse
import asyncio
import os
import sys
import uuid

from app.collector.runner import NotAuthorizedError, collect_one
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def main() -> int:
    parser = argparse.ArgumentParser(description="Collecte ponctuelle d'une source Onion v3 autorisée")
    parser.add_argument("source_id", type=uuid.UUID)
    args = parser.parse_args()
    if os.getenv("OIP_TOR_COLLECTION_ENABLED", "false").lower() != "true":
        print("Collecte Tor désactivée : OIP_TOR_COLLECTION_ENABLED=true requis", file=sys.stderr)
        return 2
    if not os.getenv("OIP_DATABASE_URL"):
        print("OIP_DATABASE_URL est requis", file=sys.stderr)
        return 4
    engine = create_engine(os.environ["OIP_DATABASE_URL"], pool_pre_ping=True)
    try:
        job_id, status = asyncio.run(collect_one(
            args.source_id, sessionmaker(bind=engine, autoflush=False, expire_on_commit=False),
        ))
    except NotAuthorizedError as exc:
        print(f"Refus : {exc}", file=sys.stderr)
        return 3
    except Exception:
        print("Erreur de persistance ou de configuration (consulter les journaux locaux)", file=sys.stderr)
        return 4
    finally:
        engine.dispose()
    print(f"job_id={job_id} status={status}")
    return 0 if status == "COMPLETED" else 1


if __name__ == "__main__":
    sys.exit(main())
