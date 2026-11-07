"""Small deterministic corpus for the MVP browser acceptance."""
from hashlib import sha256

import pytest

from app.analyzers.keywords import RuleSpec, analyze_text
from app.classifiers.rules import classify_document
from app.collector.extract import MAX_TEXT_CHARS, extract_html


@pytest.mark.parametrize(
    ("payload", "encoding", "mime", "expected", "title", "description"),
    [
        (
            b'<head><title>Atlas</title><meta name="description" content="Report &amp; notes"></head>'
            b'<nav>watchword</nav><script>watchword</script><iframe>watchword</iframe>'
            b'<svg><text>watchword</text></svg><form>watchword</form><p>Report &amp; notes</p>',
            "utf-8", "text/html", "Atlas Report & notes", "Atlas", "Report & notes",
        ),
        ("Café\tÉtude\nAtlas".encode("iso-8859-1"), "iso-8859-1", "text/plain", "Café Étude Atlas", "", ""),
        (b"Plain\xff\ttext", "unknown-encoding", "text/plain", "Plain\ufffd text", "", ""),
        (b"<nav>watchword</nav><script>watchword</script>", "utf-8", "text/html", "", "", ""),
        (b"<p>watchword</p><p>watchwords</p>", "utf-8", "text/html", "watchword watchwords", "", ""),
    ],
    ids=["excluded-active-and-navigation", "latin1", "fallback-decoding", "empty-visible", "whole-word"],
)
def test_extraction_corpus(payload, encoding, mime, expected, title, description, valid_onion_url):
    extracted = extract_html(payload, encoding, content_type=mime, page_url=valid_onion_url)
    assert (extracted.transient_text, extracted.title, extracted.description) == (expected, title, description)
    assert extracted.text_length == len(expected)
    assert extracted.text_sha256 == sha256(expected.encode()).hexdigest()
    matches = analyze_text(extracted.transient_text, [RuleSpec("watch", "watchword", 10)])
    assert sum(hit.occurrences for hit in matches.hits) == int(expected == "watchword watchwords")


def test_same_visible_text_has_same_hash_and_limit_excludes_tail(valid_onion_url):
    first = extract_html(b"<p>Alpha beta</p><script>ignored</script>", "utf-8",
                         content_type="text/html", page_url=valid_onion_url)
    second = extract_html(b"<p>Alpha    beta</p><nav>also ignored</nav>", "utf-8",
                          content_type="text/html", page_url=valid_onion_url)
    assert first.text_sha256 == second.text_sha256
    large = extract_html(b"x" * MAX_TEXT_CHARS + b" watchword", "utf-8",
                         content_type="text/plain", page_url=valid_onion_url)
    assert large.text_length == MAX_TEXT_CHARS
    assert large.text_sha256 == sha256(b"x" * MAX_TEXT_CHARS).hexdigest()
    assert not analyze_text(large.transient_text, [RuleSpec("watch", "watchword", 10)]).hits


def test_contextual_cti_example_remains_an_unverified_claim():
    result = classify_document('Synthetic news article says no stolen database has been found.')
    assert {category.category for category in result.categories} == {"NEWS", "SUSPECTED_DATA_LEAK"}
    assert [(item.indicator_type, item.verification_status) for item in result.indicators] == [
        ("DATA_LEAK_CLAIM", "OBSERVED_CLAIM"),
    ]
