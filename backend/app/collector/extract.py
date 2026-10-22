"""Extraction locale d'un HTML non fiable. Ne charge aucune sous-ressource.

La sortie ne contient aucun corps de page conservable : digest et métadonnées
publiques bornées uniquement. Les liens Onion sont des candidats non visités.
"""
import hashlib
import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from app.security.onion import canonical_onion_root

MAX_TEXT_CHARS = 100_000
MAX_DISCOVERIES = 50
# On n'extrait que des liens href absolus ou résolus sur le même domaine,
# sans aller chercher leurs cibles ; pas de parsing généralisé du texte libre.


@dataclass(frozen=True)
class Extracted:
    title: str
    description: str
    text_sha256: str
    text_length: int
    onion_roots: tuple[str, ...]


def _clean(value: str, max_chars: int) -> str:
    # Neutralisation des contrôles et caractères invisibles dans les champs affichés.
    value = re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", unescape(value))
    return " ".join(value.split())[:max_chars]


def extract_html(body: bytes, encoding: str | None, *, content_type: str, page_url: str) -> Extracted:
    if content_type == "text/plain":
        try:
            decoded = body.decode(encoding or "utf-8", errors="replace")
        except LookupError:
            decoded = body.decode("utf-8", errors="replace")
        text = _clean(decoded, MAX_TEXT_CHARS)
        return Extracted("", "", hashlib.sha256(text.encode("utf-8")).hexdigest(), len(text), ())

    try:
        document = body.decode(encoding or "utf-8", errors="replace")
    except LookupError:
        document = body.decode("utf-8", errors="replace")
    soup = BeautifulSoup(document, "html.parser")
    title = _clean(soup.title.get_text(" ", strip=True), 240) if soup.title else ""
    description = ""
    for meta in soup.find_all("meta", attrs={"name": True}):
        if (meta.get("name") or "").lower() == "description":
            description = _clean(str(meta.get("content") or ""), 500)
            break
    candidates: set[str] = set()
    for anchor in soup.find_all("a", href=True, limit=500):
        raw = anchor.get("href")
        if not isinstance(raw, str) or len(raw) > 512:
            continue
        try:
            parsed = urlsplit(urljoin(page_url, raw.strip()))
            if (not parsed.hostname or not parsed.hostname.lower().endswith(".onion")
                    or parsed.username is not None or parsed.password is not None or parsed.port is not None):
                continue
            root = canonical_onion_root(f"{parsed.scheme}://{parsed.hostname}/")
            if root != page_url:
                candidates.add(root)
        except ValueError:
            pass
        if len(candidates) >= MAX_DISCOVERIES:
            break
    for node in soup(["script", "style", "noscript", "iframe", "svg", "nav", "footer", "header"]):
        node.decompose()
    text = _clean(soup.get_text(" ", strip=True), MAX_TEXT_CHARS)
    return Extracted(title, description, hashlib.sha256(text.encode("utf-8")).hexdigest(), len(text), tuple(sorted(candidates)))
