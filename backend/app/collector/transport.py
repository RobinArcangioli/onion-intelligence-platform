"""HTTP textuel strict via SOCKS5 Tor, sans route directe de secours."""
from dataclasses import dataclass

import httpx

from app.security.onion import canonical_onion_root

MAX_BODY = 256 * 1024
SOCKS_PROXY = "socks5://tor:9050"
ALLOWED_TYPES = {"text/html", "text/plain"}


class CollectError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Fetched:
    status: int
    content_type: str
    encoding: str | None
    body: bytes


async def fetch_onion_root(url: str, *, proxy: str = SOCKS_PROXY) -> Fetched:
    """Seul un root Onion v3 est accepté ; proxy obligatoire, pas de redirection.

    L'injection du proxy sert exclusivement aux tests et ne provient pas des
    entrées utilisateur ni de l'API. En production le CLI passe toujours Tor.
    """
    if canonical_onion_root(url) != url:
        raise CollectError("INVALID_SOURCE")
    if not proxy.startswith("socks5://"):
        raise CollectError("PROXY_REQUIRED")
    try:
        async with httpx.AsyncClient(
            proxy=proxy, trust_env=False, follow_redirects=False,
            timeout=httpx.Timeout(connect=35.0, read=25.0, write=10.0, pool=5.0),
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
            headers={"User-Agent": "OIP-CTI/0.3 (public-text-only)", "Accept": "text/html, text/plain", "Accept-Encoding": "identity"},
        ) as client:
            async with client.stream("GET", url) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    raise CollectError("REDIRECT_BLOCKED")
                if response.status_code != 200:
                    raise CollectError("HTTP_NOT_OK")
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower().strip()
                if content_type not in ALLOWED_TYPES:
                    raise CollectError("MIME_BLOCKED")
                if response.headers.get("content-encoding", "identity").lower().strip() != "identity":
                    raise CollectError("ENCODING_BLOCKED")
                reported = response.headers.get("content-length")
                if reported and reported.isdigit() and int(reported) > MAX_BODY:
                    raise CollectError("BODY_TOO_LARGE")
                body = bytearray()
                # Les octets RAW empêchent le décodage de bombes de compression.
                async for chunk in response.aiter_raw(chunk_size=8192):
                    if len(body) + len(chunk) > MAX_BODY:
                        raise CollectError("BODY_TOO_LARGE")
                    body.extend(chunk)
                return Fetched(response.status_code, content_type, response.encoding, bytes(body))
    except (httpx.TimeoutException, httpx.NetworkError, httpx.ProxyError, httpx.ProtocolError) as exc:
        raise CollectError("TOR_NETWORK_ERROR") from exc
