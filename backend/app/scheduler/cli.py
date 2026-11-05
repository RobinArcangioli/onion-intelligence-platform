"""Run DB-only scheduler explicitly; no Tor dependencies or HTTP requests."""
import argparse
import json
import sys
import time
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.scheduler.service import dispatch_due, scheduler_authorized


def main() -> int:
    parser = argparse.ArgumentParser(description="OIP governed scheduler (off by default)")
    parser.add_argument("mode", choices=["once", "loop"])
    parser.add_argument("--interval", type=int, default=60, help="loop seconds (30..3600)")
    args = parser.parse_args()
    if not 30 <= args.interval <= 3600:
        parser.error("interval must be 30..3600")
    try:
        if not scheduler_authorized():
            print("Scheduler disabled; no database mutation", flush=True)
            return 0
        engine = create_engine(os.environ["OIP_DATABASE_URL"], pool_pre_ping=True)
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        while True:
            print(json.dumps(dispatch_due(factory), sort_keys=True), flush=True)
            if args.mode == "once":
                return 0
            time.sleep(args.interval)
    except Exception as exc:
        # Fail closed; no URLs, credentials or DB errors in scheduler logs.
        print(f"Scheduler stopped: {type(exc).__name__}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
