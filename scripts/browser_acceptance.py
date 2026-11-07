"""Synthetic browser fixtures for the real OIP queue and analysis paths."""
import asyncio
from contextlib import asynccontextmanager, suppress
from html import escape
import os

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.collector.transport import CollectError, Fetched
from app.collector.worker import process_one
from app.security.api_key import require_api_key, require_role

ACTIVE_MARKUP = '<img src="/fixture-must-not-load" onerror="window.__oipInjected=1">'


class Switch(BaseModel):
    enabled: bool


def install_acceptance(app, factory, *, root: str, discovered: str) -> None:
    router = APIRouter(prefix="/api/v1/demo/acceptance", dependencies=[
        Depends(require_api_key), Depends(require_role("ADMIN")),
    ])
    blocked = asyncio.Event()
    visited: list[str] = []
    pages = {
        root + "catalogue": Fetched(200, "text/html", "utf-8", f"""
            <html><head><title>{escape(ACTIVE_MARKUP)}</title>
            <meta name="description" content="{escape(ACTIVE_MARKUP, quote=True)}"></head>
            <body><nav>nav-only-trigger</nav>
            <script src="/fixture-must-not-load">window.__oipInjected=1; script-only-trigger;</script>
            <img src="/fixture-must-not-load" onerror="window.__oipInjected=1">
            <iframe src="/fixture-must-not-load"></iframe>
            <main><p>Signal visible atlasneedle.</p>
            <a href="{discovered}listing">Adresse candidate</a></main></body></html>
        """.encode()),
        root + "notes": Fetched(200, "text/plain", "utf-8", b"Independent synthetic notes."),
    }

    async def fetch(url):
        visited.append(url)
        if url == root:
            await blocked.wait()
            return Fetched(200, "text/html", "utf-8", b"<p>Checking your browser. Please wait.</p>")
        if url not in pages:
            raise CollectError("UNEXPECTED_FIXTURE_URL")
        return pages[url]

    async def work():
        while True:
            await process_one(factory, fetcher=fetch)
            await asyncio.sleep(0.1)

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(work())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    @router.get("")
    async def fixture():
        return {"root": root, "discovered": discovered, "visited": list(visited)}

    @router.post("/release")
    async def release():
        blocked.set()
        return {"released": True}

    @router.put("/emergency-stop")
    async def emergency_stop(payload: Switch):
        os.environ["OIP_COLLECTION_EMERGENCY_STOP"] = "true" if payload.enabled else "false"
        return {"enabled": payload.enabled}

    app.router.lifespan_context = lifespan
    app.include_router(router)
