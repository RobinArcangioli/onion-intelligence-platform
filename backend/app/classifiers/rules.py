"""Versioned, conservative documentary signals. All input text is ephemeral.

These are *heuristic suggestions*, NOT proof of site purpose, criminal activity,
or veracity of any claim. No quotes, credentials, page bodies or matched terms
are persisted. A rule's code, not the suspicious string, is retained.
"""
from dataclasses import dataclass
import re
from app.analyzers.keywords import normalized_phrase

RULESET_VERSION = "2026-10-lot4-v1"
MAX_CVE_REFERENCES = 20
MAX_CLASSIFICATIONS = 8

# Deliberately limited, publicly discussable documentary vocabulary. A term in
# a news report can trigger a false positive; operator review is essential.
CATEGORY_RULES: dict[str, tuple[tuple[str, str], ...]] = {
    "NEWS": (("NEWS_1", "press release"), ("NEWS_2", "news article"), ("NEWS_3", "news desk")),
    "FORUM": (("FORUM_1", "discussion forum"), ("FORUM_2", "forum thread")),
    "DOCUMENT_SHARING": (("DOC_1", "document repository"), ("DOC_2", "document archive")),
    "ONION_DIRECTORY": (("DIR_1", "onion directory"), ("DIR_2", "onion links directory")),
    "CYBERCRIME_FORUM": (("CFORUM_1", "initial access broker"), ("CFORUM_2", "criminal forum")),
    "RANSOMWARE_LEAK_SITE": (("RLEAK_1", "ransomware leak site"), ("RLEAK_2", "ransomware victim list")),
    "SUSPECTED_DATA_LEAK": (("DLEAK_1", "stolen database"), ("DLEAK_2", "leaked customer records")),
    "FRAUD_RELATED": (("FRAUD_1", "phishing kit"), ("FRAUD_2", "carding marketplace")),
    "EXTREMIST_PROPAGANDA": (("EXT_1", "extremist propaganda"), ("EXT_2", "extremist recruitment")),
    "SUSPECTED_CHILD_EXPLOITATION": (("CHILD_1", "child sexual abuse material"), ("CHILD_2", "csam trading")),
}

# These signals indicate allegations/references, not confirmed events.
CLAIM_RULES: dict[str, tuple[tuple[str, str], ...]] = {
    "RANSOMWARE_CLAIM": (("RANSOM_1", "ransomware victim list"), ("RANSOM_2", "ransomware leak")),
    "DATA_LEAK_CLAIM": (("DATA_1", "stolen database"), ("DATA_2", "leaked customer records")),
    "ACCESS_SALE_CLAIM": (("ACCESS_1", "initial access for sale"), ("ACCESS_2", "selling corporate access")),
}

SENSITIVE_CATEGORIES = frozenset({"SUSPECTED_CHILD_EXPLOITATION", "EXTREMIST_PROPAGANDA"})
QUARANTINE_CATEGORIES = frozenset({"SUSPECTED_CHILD_EXPLOITATION"})
CVE_PATTERN = re.compile(r"(?<![\w-])CVE-(20\d{2})-(\d{4,8})(?![\w-])", re.IGNORECASE)


@dataclass(frozen=True)
class CategorySuggestion:
    category: str
    confidence: int
    evidence_codes: tuple[str, ...]
    review_status: str


@dataclass(frozen=True)
class IndicatorSuggestion:
    indicator_type: str
    public_reference: str  # CVE only; empty for allegations
    verification_status: str
    confidence: int
    evidence_codes: tuple[str, ...]


@dataclass(frozen=True)
class Classification:
    categories: tuple[CategorySuggestion, ...]
    indicators: tuple[IndicatorSuggestion, ...]
    quarantine: bool


def _signals(text: str, rule_set: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    matches: list[str] = []
    for code, phrase in rule_set:
        if re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text):
            matches.append(code)
    return tuple(matches)


def classify_document(text: str, *, title: str = "", description: str = "") -> Classification:
    """No I/O. Deterministic rules, bounded results and conservative confidence.

    confidence is a heuristic *evidence strength*, not calibrated probability.
    Neither relevance nor number of hits imply that a published claim is true.
    """
    normalized = normalized_phrase(" ".join((title[:240], description[:500], text[:100_000])))
    categories = []
    for category, rules in CATEGORY_RULES.items():
        codes = _signals(normalized, rules)
        if codes:
            categories.append(CategorySuggestion(
                category, min(75, 30 + 15 * len(codes)), codes,
                "REVIEW_REQUIRED" if category in SENSITIVE_CATEGORIES else "AUTO_SUGGESTED",
            ))
    # Safety signals must be evaluated BEFORE the presentation cap, otherwise
    # a page matching many ordinary categories could hide a sensitive one.
    quarantine = any(c.category in QUARANTINE_CATEGORIES for c in categories)
    # Minimize stored metadata when a high-risk indicator is detected. Do not
    # retain additional classifications, references or other derived details.
    if quarantine:
        sensitive = next(c for c in categories if c.category in QUARANTINE_CATEGORIES)
        return Classification((sensitive,), (), True)
    categories = categories[:MAX_CLASSIFICATIONS]

    indicators = []
    for kind, rules in CLAIM_RULES.items():
        codes = _signals(normalized, rules)
        if codes:
            indicators.append(IndicatorSuggestion(kind, "", "OBSERVED_CLAIM", min(70, 30 + 15*len(codes)), codes))
    found = set()
    for match in CVE_PATTERN.finditer(normalized):
        year = int(match.group(1))
        if not 2000 <= year <= 2099:
            continue
        # Only public CVE labels are persisted; never IPs, hashes, credentials or datasets.
        value = f"CVE-{year}-{match.group(2)}"
        if value not in found:
            found.add(value)
            indicators.append(IndicatorSuggestion("PUBLIC_CVE_REFERENCE", value,
                "OBSERVED_REFERENCE", 65, ("CVE_PATTERN",)))
        if len(found) >= MAX_CVE_REFERENCES:
            break
    return Classification(tuple(categories), tuple(indicators), False)


def taxonomy() -> list[dict]:
    return [{"category": name, "review_required": name in SENSITIVE_CATEGORIES,
             "rule_codes": [code for code, _ in rules], "ruleset_version": RULESET_VERSION}
            for name, rules in CATEGORY_RULES.items()]
