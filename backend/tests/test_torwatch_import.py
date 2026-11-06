import asyncio
import base64
import hashlib
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "import-torwatch.py"
spec = importlib.util.spec_from_file_location("torwatch_import", SCRIPT)
torwatch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(torwatch)


def onion(seed):
    key = bytes([seed]) * 32
    version = b"\x03"
    checksum = hashlib.sha3_256(b".onion checksum" + key + version).digest()[:2]
    host = base64.b32encode(key + checksum + version).decode().lower()
    return f"http://{host}.onion/"


def test_only_first_ten_unique_market_cards():
    market_links = "".join(
        f'<a href="/service/market-{i}" aria-label="View market {i}"></a>' * 2
        for i in range(12)
    )
    html = f"""
      <a href="/service/sponsored" aria-label="View sponsored"></a>
      <section id="block-0"><h2>MARKETS</h2>
      <a href="//example.test/service/fake" aria-label="View fake"></a>
      {market_links}</section>
    """
    assert torwatch.market_paths(html) == [f"/service/market-{i}" for i in range(10)]
    with pytest.raises(ValueError, match="Markets"):
        torwatch.market_paths("<title>Just a moment...</title>")


def test_detail_reads_only_service_roots_in_display_order():
    first, second, outside = (onion(i) for i in range(3))
    html = f"""
      <h1>Fictional Market</h1>
      <section><h2>Also on</h2><a href="{outside}">Related</a></section>
      <section><div><h2>Service URLs · 2 total</h2></div>
        <a href="{first}">One</a><a href="{first}">Duplicate</a>
        <a href="{second}login">Non-root</a><a href="{second}">Two</a>
      </section>
    """
    assert torwatch.detail(html, "/service/test") == {
        "path": "/service/test", "name": "Fictional Market", "mirrors": [first, second]
    }


def test_probe_skips_invalid_and_duplicate_roots_and_stops_after_first_available():
    first, second, third = (onion(i) for i in range(3))
    seen = []

    async def probe(url):
        seen.append(url)
        return url == second

    assert asyncio.run(torwatch.first_available(
        ["http://example.test/", first, first.rstrip("/"), second, third], probe
    )) == second
    assert seen == [first, second]


def test_snapshot_rejects_foreign_paths_and_non_onion_targets():
    catalog = [{"path": f"/service/market-{i}", "name": f"Market {i}", "mirrors": [onion(i)]}
               for i in range(10)]
    assert torwatch.validated_catalog(catalog) == catalog
    with pytest.raises(ValueError, match="dupliqué"):
        torwatch.validated_catalog([catalog[0], *catalog[:-1]])
    catalog[0]["mirrors"] = ["http://127.0.0.1/"]
    with pytest.raises(ValueError, match="Onion"):
        torwatch.validated_catalog(catalog)
