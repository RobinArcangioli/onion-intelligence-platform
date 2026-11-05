"""Normalize ONLY public CVE identifiers; never persist arbitrary page IOCs."""
import re

_CVE = re.compile(r"CVE-(20[0-9]{2})-([0-9]{4,8})", re.IGNORECASE | re.ASCII)


def canonical_cve(value: str) -> str | None:
    """Strict full-string validation (no prefixes, URLs, credentials or whitespace)."""
    matched = _CVE.fullmatch(value)
    if not matched:
        return None
    return f"CVE-{matched.group(1)}-{matched.group(2)}"
