import pytest

from app.security.onion import canonical_onion_root


@pytest.mark.parametrize("value", [
    "http://example.com/",
    "https://localhost/",
    "http://notv3.onion/",
    "file:///etc/passwd",
    "http://user:pass@aaaaaaaa.onion/",
    "http://127.0.0.1/",
])
def test_invalid_urls_rejected(value: str):
    with pytest.raises(ValueError):
        canonical_onion_root(value)


def test_valid_v3_url_normalized(valid_onion_url: str):
    assert canonical_onion_root(valid_onion_url[:-1]) == valid_onion_url


def test_no_path_or_query(valid_onion_url: str):
    with pytest.raises(ValueError):
        canonical_onion_root(valid_onion_url + "secret")
    with pytest.raises(ValueError):
        canonical_onion_root(valid_onion_url + "?download=1")


def test_corrupted_v3_checksum_rejected(valid_onion_url: str):
    corrupted = valid_onion_url.replace("aaaq", "baaq", 1)
    with pytest.raises(ValueError, match="Checksum"):
        canonical_onion_root(corrupted)
