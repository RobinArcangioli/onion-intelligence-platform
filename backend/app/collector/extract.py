"""Offline-only bounded extraction. The page text is ephemeral and NEVER stored.

No scripts, subresources, redirects or newly-discovered URL are fetched here.
Candidate .onion addresses are syntactically verified v3 hosts only.
"""
from dataclasses import dataclass, field
import hashlib
from html import unescape
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
from app.security.onion import canonical_onion_root

MAX_TEXT_CHARS = 100_000
MAX_DISCOVERIES = 50
# A full v3 onion host + optional http scheme. Boundaries and checksum validated.
MENTION = re.compile(r"(?<![a-z2-7])(?:https?://)?([a-z2-7]{56}\.onion)(?![a-z0-9.-])", re.I)


@dataclass(frozen=True)
class Candidate:
    root: str
    evidence_kind: str  # LINK, TEXT, BOTH


@dataclass(frozen=True)
class Extracted:
    title: str
    description: str
    text_sha256: str
    text_length: int
    onion_roots: tuple[str, ...]
    # Ephemeral, never part of DB models or API schemas.
    transient_text: str = field(default="", repr=False, compare=False)
    candidates: tuple[Candidate, ...] = ()


def _clean(value: str, max_chars: int) -> str:
    value = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", unescape(value))
    return " ".join(value.split())[:max_chars]


def _candidate(raw: str) -> str | None:
    try:
        return canonical_onion_root(raw)
    except ValueError:
        return None


def _extract_candidates(page_url: str, hrefs: list[str], text: str) -> tuple[Candidate, ...]:
    discovered: dict[str, set[str]] = {}
    current_host = urlsplit(page_url).hostname
    for href in hrefs[:500]:
        if len(href) > 512:
            continue
        try:
            parsed = urlsplit(urljoin(page_url, href.strip()))
            if (not parsed.hostname or not parsed.hostname.lower().endswith(".onion")
                    or parsed.username or parsed.password or parsed.port is not None):
                continue
            root = _candidate(f"{parsed.scheme}://{parsed.hostname}/")
            if root and parsed.hostname != current_host:
                existing = next((r for r in discovered if urlsplit(r).hostname == parsed.hostname), None)
                if existing or len(discovered) < MAX_DISCOVERIES:
                    discovered.setdefault(existing or root, set()).add("LINK")
        except ValueError:
            continue
        if len(discovered) >= MAX_DISCOVERIES:
            break
    # Scan text already stripped of active/non-visible HTML elements.
    for match in MENTION.finditer(text):
        host = match.group(1).lower()
        if host == current_host:
            continue
        root = _candidate("http://" + host + "/")
        if root:
            # Treat http and https links to the same host as one candidate.
            existing = next((r for r in discovered if urlsplit(r).hostname == host), None)
            if existing or len(discovered) < MAX_DISCOVERIES:
                discovered.setdefault(existing or root, set()).add("TEXT")
        if len(discovered) >= MAX_DISCOVERIES:
            break
    return tuple(Candidate(root, "BOTH" if len(kinds) == 2 else next(iter(kinds)))
                 for root, kinds in sorted(discovered.items()))


def extract_html(body: bytes, encoding: str | None, *, content_type: str, page_url: str) -> Extracted:
    try:
        document = body.decode(encoding or "utf-8", errors="replace")
    except LookupError:
        document = body.decode("utf-8", errors="replace")
    if content_type == "text/plain":
        text = _clean(document, MAX_TEXT_CHARS)
        candidates = _extract_candidates(page_url, [], text)
        return Extracted("", "", hashlib.sha256(text.encode()).hexdigest(),
                         len(text), tuple(x.root for x in candidates), text, candidates)

    soup = BeautifulSoup(document, "html.parser")
    title = _clean(soup.title.get_text(" ", strip=True), 240) if soup.title else ""
    description = ""
    for meta in soup.find_all("meta", attrs={"name": True}):
        if (meta.get("name") or "").lower() == "description":
            description = _clean(str(meta.get("content") or ""), 500)
            break
    # Remove untrusted active and decorative elements before text or href scanning.
    for node in soup(["script", "style", "noscript", "iframe", "svg", "nav", "footer", "header", "form", "template"]):
        node.decompose()
    hrefs = [str(a.get("href")) for a in soup.find_all("a", href=True, limit=500) if isinstance(a.get("href"), str)]
    text = _clean(soup.get_text(" ", strip=True), MAX_TEXT_CHARS)
    candidates = _extract_candidates(page_url, hrefs, text)
    return Extracted(title, description, hashlib.sha256(text.encode()).hexdigest(),
                     len(text), tuple(x.root for x in candidates), text, candidates)
