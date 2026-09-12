import pytest
from fastapi import HTTPException

from app.core.api_keys import parse_api_keys
from app.core.auth import require_api_key
from app.core.config import settings
from app.core.rate_limit import RateLimiter, limiter


@pytest.fixture(autouse=True)
def clean_limiter():
    """The limiter is process-wide, so one test's requests would otherwise
    count against the next one's allowance."""
    limiter.reset()
    yield
    limiter.reset()


class TestFailsClosed:
    """No keys configured. The gateway must not serve itself openly."""

    async def test_unconfigured_gateway_refuses_requests(self, monkeypatch):
        """A deployment that forgot GATEWAY_API_KEYS used to serve everything
        to anyone, indefinitely and silently. Now it refuses, loudly."""
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "")
        monkeypatch.setattr(settings, "GATEWAY_ALLOW_ANONYMOUS", False)

        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(api_key=None)

        assert exc_info.value.status_code == 503
        # The error has to name the way out, or it is just an outage.
        assert "GATEWAY_API_KEYS" in exc_info.value.detail
        assert "GATEWAY_ALLOW_ANONYMOUS" in exc_info.value.detail

    async def test_presenting_a_key_does_not_help_when_none_configured(
        self, monkeypatch
    ):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "")
        monkeypatch.setattr(settings, "GATEWAY_ALLOW_ANONYMOUS", False)

        with pytest.raises(HTTPException):
            await require_api_key(api_key="hopeful-guess")


class TestAnonymousOptOut:
    """Explicitly opted out, as local development does."""

    async def test_no_key_allowed(self, monkeypatch):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "")
        monkeypatch.setattr(settings, "GATEWAY_ALLOW_ANONYMOUS", True)

        result = await require_api_key(api_key=None)
        assert result.name == "anonymous"

    async def test_anonymous_is_not_rate_limited(self, monkeypatch):
        """Local development should not trip a limit while poking at the API."""
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "")
        monkeypatch.setattr(settings, "GATEWAY_ALLOW_ANONYMOUS", True)

        for _ in range(300):
            await require_api_key(api_key=None)


class TestKeyMatching:
    async def test_correct_key_allowed(self, monkeypatch):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "a:secret-1,b:secret-2")
        result = await require_api_key(api_key="secret-2")
        assert result.name == "b"

    async def test_missing_key_rejected(self, monkeypatch):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "a:secret-1")
        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(api_key=None)
        assert exc_info.value.status_code == 401

    async def test_wrong_key_rejected(self, monkeypatch):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "a:secret-1")
        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(api_key="not-the-right-key")
        assert exc_info.value.status_code == 401

    async def test_bare_secrets_still_work(self, monkeypatch):
        """Existing deployments configured before names existed must keep
        working across an upgrade."""
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "legacy-key-1,legacy-key-2")
        result = await require_api_key(api_key="legacy-key-2")
        assert result.secret == "legacy-key-2"
        assert result.name == "unnamed"

    async def test_whitespace_in_config_is_tolerated(self, monkeypatch):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", " a:key-a , b:key-b ")
        result = await require_api_key(api_key="key-b")
        assert result.name == "b"


class TestRateLimiting:
    async def test_key_is_limited_at_its_configured_rate(self, monkeypatch):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "small:secret:3")

        for _ in range(3):
            await require_api_key(api_key="secret")

        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(api_key="secret")

        assert exc_info.value.status_code == 429
        assert exc_info.value.headers["Retry-After"]

    async def test_one_consumer_cannot_exhaust_another(self, monkeypatch):
        """The whole point: a runaway client must not starve everyone else,
        including the sync jobs sharing this process."""
        monkeypatch.setattr(
            settings, "GATEWAY_API_KEYS", "noisy:secret-a:2,quiet:secret-b:2"
        )

        for _ in range(2):
            await require_api_key(api_key="secret-a")
        with pytest.raises(HTTPException):
            await require_api_key(api_key="secret-a")

        # Unaffected.
        result = await require_api_key(api_key="secret-b")
        assert result.name == "quiet"

    async def test_keys_without_their_own_limit_use_the_default(self, monkeypatch):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "plain:secret")
        monkeypatch.setattr(settings, "DEFAULT_RATE_LIMIT_PER_MINUTE", 2)

        for _ in range(2):
            await require_api_key(api_key="secret")
        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(api_key="secret")
        assert exc_info.value.status_code == 429


class TestParsing:
    def test_name_secret_and_limit(self):
        [key] = parse_api_keys("predify:s3cret:120", default_rpm=60)
        assert (key.name, key.secret, key.requests_per_minute) == (
            "predify", "s3cret", 120,
        )

    def test_a_secret_containing_a_colon_is_not_mistaken_for_a_name(self):
        """Only a plausible identifier before the colon means "named". A
        generated secret with punctuation in it stays one secret."""
        [key] = parse_api_keys("abc!def:ghi", default_rpm=60)
        assert key.secret == "abc!def:ghi"
        assert key.name == "unnamed"

    def test_a_bad_rate_limit_does_not_revoke_the_key(self):
        """A typo in a number should cost the default limit, not access."""
        [key] = parse_api_keys("predify:s3cret:not-a-number", default_rpm=60)
        assert key.requests_per_minute == 60

    def test_empty_entries_are_skipped(self):
        assert parse_api_keys(" , ,", default_rpm=60) == []

    def test_str_never_leaks_the_secret(self):
        [key] = parse_api_keys("predify:very-secret:30", default_rpm=60)
        assert "very-secret" not in str(key)
        assert "predify" in str(key)


class TestSlidingWindow:
    def test_window_slides_rather_than_resetting_on_a_boundary(self):
        """A fixed window lets a caller limited to N per minute send 2N in a
        moment by straddling the boundary."""
        rl = RateLimiter(window_seconds=60)
        for _ in range(3):
            assert rl.check("k", limit=3) is None
        assert rl.check("k", limit=3) is not None

    def test_retry_after_is_at_least_one_second(self):
        rl = RateLimiter(window_seconds=60)
        rl.check("k", limit=1)
        assert rl.check("k", limit=1) >= 1

    def test_zero_limit_means_unlimited(self):
        rl = RateLimiter()
        for _ in range(500):
            assert rl.check("k", limit=0) is None
