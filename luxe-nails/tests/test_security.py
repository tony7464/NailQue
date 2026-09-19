from nailque.security import RateLimiter, hash_secret, is_hashed_secret, request_client_ip, verify_secret
from nailque.updates import assert_https_github_url, is_newer_version, normalize_version


def test_password_hash_round_trip():
    hashed = hash_secret("secret-pin")
    assert is_hashed_secret(hashed)
    matched, needs_rehash = verify_secret(hashed, "secret-pin")
    assert matched is True
    assert needs_rehash is False
    matched, _ = verify_secret(hashed, "wrong")
    assert matched is False


def test_plaintext_secret_is_upgraded():
    matched, needs_rehash = verify_secret("1234", "1234")
    assert matched is True
    assert needs_rehash is True


def test_forwarded_for_ignored_without_trusted_proxy():
    ip = request_client_ip("127.0.0.1", "8.8.8.8", trust_proxy=False)
    assert ip == "127.0.0.1"


def test_forwarded_for_used_with_trusted_proxy():
    ip = request_client_ip("127.0.0.1", "10.0.0.8, 10.0.0.1", trust_proxy=True)
    assert ip == "10.0.0.8"


def test_rate_limiter_blocks_after_limit():
    limiter = RateLimiter()
    assert limiter.allow("login:1", limit=2, window_seconds=60)
    assert limiter.allow("login:1", limit=2, window_seconds=60)
    assert limiter.allow("login:1", limit=2, window_seconds=60) is False


def test_version_compare():
    assert normalize_version("v3.1.0") == (3, 1, 0)
    assert is_newer_version("3.1.0", "3.0.0")
    assert not is_newer_version("3.0.0", "3.0.0")


def test_update_url_must_be_github_https():
    assert_https_github_url("https://github.com/owner/repo/releases/download/v1/app.pkg")
    try:
        assert_https_github_url("http://evil.example/malware.exe")
        assert False, "expected insecure URL to fail"
    except RuntimeError:
        pass
