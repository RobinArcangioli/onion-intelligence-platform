"""Bounded exact phrase matching. No regex input or page text is persisted.

Scoring explains *relevance to operator rules*, not harmfulness, truth or illegality.
"""
from dataclasses import dataclass
import re
import unicodedata

MAX_RULES_PER_JOB = 200
MAX_OCCURRENCES_PER_RULE = 20


@dataclass(frozen=True)
class RuleSpec:
    id: object
    phrase: str
    weight: int


@dataclass(frozen=True)
class RuleHit:
    rule_id: object
    occurrences: int
    contribution: int


@dataclass(frozen=True)
class Analysis:
    score: int
    hits: tuple[RuleHit, ...]


def normalized_phrase(value: str) -> str:
    """Casefold and space-normalize without stripping arbitrary punctuation."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def analyze_text(text: str, rules: list[RuleSpec]) -> Analysis:
    """Return counts and a capped, additive, deterministic score (0..100).

    Boundaries avoid matching 'cat' in 'catalog'. The text stays in memory only.
    score = min(100, sum(min(occurrences, 3) * rule.weight)).
    """
    haystack = normalized_phrase(text)
    hits: list[RuleHit] = []
    for rule in rules[:MAX_RULES_PER_JOB]:
        phrase = normalized_phrase(rule.phrase)
        if not phrase or not 1 <= rule.weight <= 30:
            continue
        # re.escape prevents arbitrary regular expressions in operator inputs.
        pattern = re.compile(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)")
        count = 0
        for _ in pattern.finditer(haystack):
            count += 1
            if count == MAX_OCCURRENCES_PER_RULE:
                break
        if count:
            hits.append(RuleHit(rule.id, count, min(count, 3) * rule.weight))
    return Analysis(min(100, sum(hit.contribution for hit in hits)), tuple(hits))
