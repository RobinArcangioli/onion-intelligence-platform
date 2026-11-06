"""Validation syntaxique stricte des adresses Onion v3; aucune requête réseau."""
import base64
import hashlib
import re
from urllib.parse import urlsplit

ONION_V3_HOST = re.compile(r"^[a-z2-7]{56}\.onion$")


def canonical_onion_root(raw: str) -> str:
    if not isinstance(raw, str) or len(raw) > 255:
        raise ValueError("URL Onion invalide")
    try:
        parsed = urlsplit(raw.strip())
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("URL Onion invalide") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or not ONION_V3_HOST.fullmatch(hostname.lower())
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Seules les racines HTTP(S) des services Onion v3 sont acceptées")
    encoded = hostname.lower()[:-6]
    try:
        decoded = base64.b32decode(encoded.upper(), casefold=False)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError("Adresse Onion v3 mal encodée") from exc
    if len(decoded) != 35:
        raise ValueError("Longueur Onion v3 incorrecte")
    public_key, checksum, version = decoded[:32], decoded[32:34], decoded[34]
    expected = hashlib.sha3_256(b".onion checksum" + public_key + b"\x03").digest()[:2]
    if version != 3 or checksum != expected:
        raise ValueError("Checksum Onion v3 invalide")
    return f"{parsed.scheme}://{hostname.lower()}/"


# Keep the root validator for discovery/import callers. Collection addresses
# additionally accept ordinary paths, without query strings or fragments.
_ONION_PATH = re.compile(r"/[A-Za-z0-9_~./-]*")


def canonical_onion_page(raw: str) -> str:
    if not isinstance(raw, str) or len(raw) > 255:
        raise ValueError("URL Onion invalide")
    raw = raw.strip()
    if any(ord(char) <= 32 or ord(char) == 127 for char in raw) or "?" in raw or "#" in raw:
        raise ValueError("L’adresse ne doit contenir ni paramètres, ni fragment, ni espace")
    parsed = urlsplit(raw)
    root = canonical_onion_root(f"{parsed.scheme}://{parsed.netloc}/")
    path = parsed.path or "/"
    if not _ONION_PATH.fullmatch(path) or "//" in path or any(part in {".", ".."} for part in path.split("/")):
        raise ValueError("Chemin Onion invalide")
    return root.rstrip("/") + path
