#!/usr/bin/env python3
"""Import the first ten Tor.watch Markets as unapproved local source candidates."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

ORIGIN = "https://tor.watch/"
MARKET_LIMIT = 10
MIRROR_LIMIT = 24
SERVICE_PATH = re.compile(r"/service/(?:[a-zA-Z0-9_.~-]|%[a-fA-F0-9]{2}){1,160}")
ONION_ROOT = re.compile(r"https?://[a-z2-7]{56}\.onion/?", re.IGNORECASE)
DOCKER = ("docker", "--host", "unix:///var/run/docker.sock")


def market_paths(html):
    soup = BeautifulSoup(html, "html.parser")
    block = soup.select_one("#block-0")
    if block is None or block.get_text(" ", strip=True).upper().split()[:1] != ["MARKETS"]:
        raise ValueError("Section Markets introuvable dans la page Tor.watch.")
    paths = dict.fromkeys(
        link["href"] for link in block.select('a[href][aria-label^="View "]')
        if SERVICE_PATH.fullmatch(link["href"])
    )
    return list(paths)[:MARKET_LIMIT]


def detail(html, path):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.find("h1")
    heading = next((h for h in soup.find_all("h2")
                    if h.get_text(" ", strip=True).startswith("Service URLs")), None)
    section = heading.find_parent("section") if heading else None
    if title is None or section is None:
        raise ValueError(f"Fiche ou section Service URLs introuvable : {path}")
    mirrors = dict.fromkeys(
        a["href"] for a in section.select("a[href]") if ONION_ROOT.fullmatch(a["href"])
    )
    return {"path": path, "name": title.get_text(" ", strip=True), "mirrors": list(mirrors)}


def page(client, path):
    with client.stream("GET", urljoin(ORIGIN, path)) as response:
        if response.status_code != 200:
            raise ValueError(f"Tor.watch a répondu HTTP {response.status_code} pour {path}.")
        body = bytearray()
        for chunk in response.iter_bytes(chunk_size=16384):
            body.extend(chunk)
            if len(body) > 2_000_000:
                raise ValueError("Page Tor.watch trop volumineuse.")
    return bytes(body)


def discover():
    with httpx.Client(follow_redirects=False, trust_env=False, timeout=12) as client:
        paths = market_paths(page(client, "/"))
        if len(paths) != MARKET_LIMIT:
            raise ValueError("La section Markets ne contient pas dix fiches reconnues.")
        return [detail(page(client, path), path) for path in paths]


def validated_catalog(data):
    if not isinstance(data, list) or len(data) != MARKET_LIMIT:
        raise ValueError("Un catalogue de dix fiches est attendu.")
    paths = set()
    for entry in data:
        if not isinstance(entry, dict) or set(entry) != {"path", "name", "mirrors"}:
            raise ValueError("Chaque fiche doit contenir path, name et mirrors.")
        path, name, mirrors = entry["path"], entry["name"], entry["mirrors"]
        if not isinstance(path, str) or not SERVICE_PATH.fullmatch(path) or path in paths:
            raise ValueError("Chemin de fiche Tor.watch invalide ou dupliqué.")
        if not isinstance(name, str) or not name.strip() or len(name) > 160 or any(ord(c) < 32 for c in name):
            raise ValueError("Nom de marketplace invalide.")
        if not isinstance(mirrors, list) or len(mirrors) > MIRROR_LIMIT:
            raise ValueError("Liste de miroirs invalide.")
        if any(not isinstance(url, str) or not ONION_ROOT.fullmatch(url) for url in mirrors):
            raise ValueError("Seules les racines Onion v3 sont acceptées.")
        paths.add(path)
    return data


async def first_available(mirrors, probe):
    from app.security.onion import canonical_onion_root

    seen = set()
    for mirror in mirrors:
        try:
            url = canonical_onion_root(mirror)
        except ValueError:
            continue
        if url not in seen:
            seen.add(url)
            if await probe(url):
                return url
    return None


async def run_worker(catalog, *, save):
    from sqlalchemy import create_engine, func, or_, select
    from sqlalchemy.engine import make_url
    from sqlalchemy.exc import IntegrityError, SQLAlchemyError
    from sqlalchemy.orm import sessionmaker

    from app.collector.policy import admission_lock, emergency_active, read_policy
    from app.collector.transport import ALLOWED_TYPES, SOCKS_PROXY
    from app.models import AuditLog, OnionSource, SourcePage

    policy = read_policy()
    if emergency_active(policy):
        raise ValueError("Arrêt d’urgence OIP actif.")
    factory = None
    if save:
        try:
            database_url = make_url(os.environ.get("OIP_DATABASE_URL", ""))
            if database_url.host != "db" or database_url.get_backend_name() != "postgresql":
                raise ValueError("L’import exige le service PostgreSQL db de la stack locale.")
            factory = sessionmaker(bind=create_engine(database_url, pool_pre_ping=True))
            with factory() as db:
                db.scalar(select(OnionSource.id).limit(1))
        except SQLAlchemyError:
            raise ValueError("Registre des sources indisponible dans la base locale.") from None

    limit = asyncio.Semaphore(4)
    async with httpx.AsyncClient(proxy=SOCKS_PROXY, trust_env=False, follow_redirects=False,
                                 timeout=12, limits=httpx.Limits(max_connections=4),
                                 headers={"Accept": "text/html, text/plain"}) as client:
        async def probe(url):
            async with limit:
                if emergency_active(policy):
                    raise ValueError("Arrêt d’urgence OIP actif.")
                try:
                    async with asyncio.timeout(18):
                        async with client.stream("GET", url) as response:
                            mime = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                            return response.status_code == 200 and mime in ALLOWED_TYPES
                except (httpx.RequestError, TimeoutError):
                    return False

        selected = await asyncio.gather(*(first_available(entry["mirrors"], probe) for entry in catalog))

    results = [{"name": entry["name"].strip(), "status": "REACHABLE" if url else "NO_REACHABLE_MIRROR"}
               for entry, url in zip(catalog, selected, strict=True)]
    if factory is None:
        return results
    with factory.begin() as db:
        admission_lock(db)
        for entry, url, result in zip(catalog, selected, results, strict=True):
            if url is None:
                continue
            name = result["name"]
            if emergency_active(policy):
                raise ValueError("Arrêt d’urgence OIP actif.")
            origin = urljoin(ORIGIN, entry["path"])
            existing = db.scalar(select(OnionSource.id).where(or_(
                OnionSource.canonical_url == url,
                (OnionSource.category == "MARKETPLACE") & (func.lower(OnionSource.name) == name.lower()),
                OnionSource.description == f"Catalogue Tor.watch : {origin}",
            )).limit(1))
            if existing:
                result["status"] = "ALREADY_REGISTERED"
                continue
            source = OnionSource(
                name=name, canonical_url=url, category="MARKETPLACE", priority=5,
                availability_status="AVAILABLE", approved_for_collection=False,
                collection_enabled=False, is_active=True,
                description=f"Catalogue Tor.watch : {origin}",
                authorization_note="Source candidate découverte sur Tor.watch. Approbation de collecte requise.",
            )
            try:
                with db.begin_nested():
                    db.add(source)
                    db.flush()
                    db.add(SourcePage(source_id=source.id, url=url))
                    db.add(AuditLog(actor="local_torwatch_import", action="source.import",
                                    entity_type="onion_source", entity_id=source.id,
                                    details=json.dumps({"reason": "Tor.watch marketplace candidate",
                                                        "directory_url": origin})))
            except IntegrityError:
                if db.scalar(select(OnionSource.id).where(OnionSource.canonical_url == url)) is None:
                    raise
                result["status"] = "ALREADY_REGISTERED"
            else:
                result["status"] = "CREATED"
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, help="JSON issu des fiches ouvertes dans le navigateur")
    parser.add_argument("--project", default="onion-intelligence-platform", help="Projet Docker Compose local")
    parser.add_argument("--save", action="store_true", help="Enregistrer les candidats dans la stack locale")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.worker:
            from sqlalchemy.exc import SQLAlchemyError

            catalog = validated_catalog(json.load(sys.stdin))
            try:
                results = asyncio.run(run_worker(catalog, save=args.save))
            except SQLAlchemyError:
                parser.exit(1, "Échec de l’écriture dans la base locale.\n")
            print(json.dumps(results, ensure_ascii=False))
            return 0
        if args.catalog:
            with args.catalog.open(encoding="utf-8") as source:
                catalog = validated_catalog(json.load(source))
        else:
            catalog = validated_catalog(discover())
    except (OSError, ValueError, httpx.RequestError) as exc:
        parser.exit(1, f"{exc}\n")
    try:
        workers = subprocess.check_output([
            *DOCKER, "ps", "-q", "--filter", f"label=com.docker.compose.project={args.project}",
            "--filter", "label=com.docker.compose.service=queue_worker",
        ], text=True).split()
    except (OSError, subprocess.CalledProcessError):
        parser.exit(1, "Impossible de joindre Docker sur le socket local.\n")
    if len(workers) != 1:
        parser.exit(1, "Un seul worker OIP local en cours d’exécution est attendu.\n")
    # Use the checkout's stop policy even when the running local image predates it.
    script = Path(__file__).resolve()
    policy = (script.parents[1] / "backend/app/collector/policy.py").read_text(encoding="utf-8")
    bootstrap = f"""
import importlib.util
import sys
import types

module_name = "app.collector.policy"
if importlib.util.find_spec(module_name) is None:
    module = types.ModuleType(module_name)
    sys.modules[module_name] = module
    exec(compile({policy!r}, "app/collector/policy.py", "exec"), module.__dict__)
"""
    command = [
        *DOCKER, "exec", "-i", workers[0], "python", "-c",
        bootstrap + script.read_text(encoding="utf-8"), "--worker",
    ]
    if args.save:
        command.append("--save")
    return subprocess.run(command, input=json.dumps(catalog), text=True, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
