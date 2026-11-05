"""Offline IOC candidates from explicitly labelled documentary references.

Never fetch, resolve, enrich or export indicators here. Public routable values
can be mentioned by benign pages; a mention never establishes compromise.
"""
from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import os
import re

IOC_RULESET_VERSION = "2026-10-m5b-explicit-v1"
MAX_IOCS_PER_OBSERVATION = 24
MAX_ANALYZED_CHARS = 100_000

# Deliberately require an explicit, same-line key/value field to avoid scraping
# incidental addresses, leaked tables, embedded URLs or raw credentials.
_LABEL = re.compile(r"(?<![a-zA-Z0-9_])(?P<label>domain|hostname|ipv4|ipv6|ip|sha256|sha-256)[ \t]*[:=][ \t]*", re.I)
_DOMAIN = re.compile(r"(?:[a-zA-Z0-9-]{1,63}\.){1,10}[a-zA-Z]{2,63}\.?", re.ASCII)
_IP = re.compile(r"[0-9a-fA-F:.]+", re.ASCII)
_SHA256 = re.compile(r"[0-9a-fA-F]{64}", re.ASCII)
_FORBIDDEN_TLDS = frozenset({"onion", "local", "localhost", "internal", "invalid", "test", "arpa", "example"})


@dataclass(frozen=True)
class IocMention:
    indicator_type: str
    normalized_value: str
    confidence: int
    evidence_code: str


def extraction_enabled() -> bool:
    """Fail closed: administrators must explicitly opt in via the environment."""
    return os.environ.get("OIP_IOC_EXTRACTION_ENABLED", "").lower() in {"yes", "true", "1"}


def _canonical_domain(candidate: str) -> str | None:
    value = candidate.lower().rstrip(".")
    if len(value) > 253 or _DOMAIN.fullmatch(candidate) is None:
        return None
    labels = value.split(".")
    if labels[-1] in _FORBIDDEN_TLDS:
        return None
    if any(label.startswith("-") or label.endswith("-") for label in labels):
        return None
    # Skip exact IP literals, partial addresses and single-label/internal names.
    if not any(char.isalpha() for char in value):
        return None
    return value


def canonical_ioc(indicator_type: str, value: str) -> str | None:
    """Strict canonicalization of known public IOCs; never accept URLs."""
    if not isinstance(value, str) or len(value) > 253 or any(char.isspace() for char in value):
        return None
    if indicator_type == "DOMAIN":
        return _canonical_domain(value)
    if indicator_type in {"IPV4", "IPV6"}:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            return None
        if (not address.is_global or address.is_multicast
                or getattr(address, "ipv4_mapped", None) is not None
                or (address.version == 4) != (indicator_type == "IPV4")):
            return None
        return address.compressed.lower()
    if indicator_type == "SHA256" and _SHA256.fullmatch(value):
        return value.lower()
    return None


def extract_ioc_mentions(text: str) -> tuple[IocMention, ...]:
    """Bounded, deterministic, explicit-label extraction from ephemeral text."""
    limited = text[:MAX_ANALYZED_CHARS]
    seen: set[tuple[str, str]] = set()
    found: list[IocMention] = []
    for match in _LABEL.finditer(limited):
        key = match.group("label").lower()
        start = match.end()
        if key in {"sha256", "sha-256"}:
            kind, pattern = "SHA256", _SHA256
        elif key in {"domain", "hostname"}:
            kind, pattern = "DOMAIN", _DOMAIN
        else:
            kind, pattern = "IPV4" if key == "ipv4" else "IPV6" if key == "ipv6" else "IP", _IP
        value_match = pattern.match(limited, start)
        if not value_match:
            continue
        # A regex matching only the prefix of a longer token is unsafe:
        # it could accidentally turn a secret or an URL into a candidate.
        end = value_match.end()
        if end < len(limited) and limited[end] in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-/":
            continue
        value = value_match.group()
        if kind == "IP":
            try:
                kind = "IPV4" if ipaddress.ip_address(value).version == 4 else "IPV6"
            except ValueError:
                continue
        canonical = canonical_ioc(kind, value)
        if canonical is None or (kind, canonical) in seen:
            continue
        seen.add((kind, canonical))
        found.append(IocMention(kind, canonical, 50, f"M5B_EXPLICIT_{kind}"))
        if len(found) >= MAX_IOCS_PER_OBSERVATION:
            break
    return tuple(found)
