import uuid

import pytest
from fastapi import HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.api_keys import generate_secret, parse_api_keys
from app.core.auth import require_api_key
from app.core.config import settings
from app.core.rate_limit import RateLimiter, limiter
from app.db.models.api_key import ApiKeyRecord
from app.db.models.user import User


@pytest.fixture(autouse=True)
def clean_limiter():
    """The limiter is process-wide, so one test's requests would otherwise
    count against the next one's allowance."""
    limiter.reset()
    yield
    limiter.reset()


async def _create_user_and_key(
    session: AsyncSession, *, name: str = "self-serve", requests_per_minute: int = 60
) -> str:
    """Persists a User + ApiKeyRecord and returns the plaintext secret.

    Each call is its own user - two customers can share a key `name`
    (that's exactly what one of the tests below checks), so the firebase
    uid can't be derived from `name` without colliding.
    """
    uid = f"uid-{uuid.uuid4()}"
    user = User(firebase_uid=uid, email=f"{uid}@example.com")
    session.add(user)
    await session.commit()
    await session.refresh(user)

    plaintext, prefix, hashed = generate_secret()
    record = ApiKeyRecord(
        owner_user_id=user.id,
        name=name,
        key_prefix=prefix,
        hashed_secret=hashed,
        requests_per_minute=requests_per_minute,
    )
    session.add(record)
    await session.commit()

    return plaintext


class TestFailsClosed:
    """No keys configured anywhere. The gateway must not serve itself openly."""

    async def test_unconfigured_gateway_refuses_requests(self, monkeypatch, test_session):
        """A deployment that forgot GATEWAY_API_KEYS used to serve everything
        to anyone, indefinitely and silently. Now it refuses, loudly."""
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "")
        monkeypatch.setattr(settings, "GATEWAY_ALLOW_ANONYMOUS", False)

        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(api_key=None, session=test_session)

        assert exc_info.value.status_code == 503
        # The error has to name the way out, or it is just an outage.
        assert "GATEWAY_API_KEYS" in exc_info.value.detail
        assert "GATEWAY_ALLOW_ANONYMOUS" in exc_info.value.detail

    async def test_presenting_a_key_does_not_help_when_none_configured(
        self, monkeypatch, test_session
    ):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "")
        monkeypatch.setattr(settings, "GATEWAY_ALLOW_ANONYMOUS", False)

        with pytest.raises(HTTPException):
            await require_api_key(api_key="hopeful-guess", session=test_session)

    async def test_a_live_self_serve_key_stops_the_gateway_refusing(
        self, monkeypatch, test_session
    ):
        """Zero env keys but a real self-serve customer must not be refused
        just because GATEWAY_API_KEYS was never set."""
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "")
        monkeypatch.setattr(settings, "GATEWAY_ALLOW_ANONYMOUS", False)

        plaintext = await _create_user_and_key(test_session)

        result = await require_api_key(api_key=plaintext, session=test_session)
        assert result.name == "self-serve"


class TestAnonymousOptOut:
    """Explicitly opted out, as local development does."""

    async def test_no_key_allowed(self, monkeypatch, test_session):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "")
        monkeypatch.setattr(settings, "GATEWAY_ALLOW_ANONYMOUS", True)

        result = await require_api_key(api_key=None, session=test_session)
        assert result.name == "anonymous"

    async def test_anonymous_is_not_rate_limited(self, monkeypatch, test_session):
        """Local development should not trip a limit while poking at the API."""
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "")
        monkeypatch.setattr(settings, "GATEWAY_ALLOW_ANONYMOUS", True)

        for _ in range(300):
            await require_api_key(api_key=None, session=test_session)


class TestKeyMatching:
    async def test_correct_key_allowed(self, monkeypatch, test_session):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "a:secret-1,b:secret-2")
        result = await require_api_key(api_key="secret-2", session=test_session)
        assert result.name == "b"

    async def test_missing_key_rejected(self, monkeypatch, test_session):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "a:secret-1")
        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(api_key=None, session=test_session)
        assert exc_info.value.status_code == 401

    async def test_wrong_key_rejected(self, monkeypatch, test_session):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "a:secret-1")
        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(api_key="not-the-right-key", session=test_session)
        assert exc_info.value.status_code == 401

    async def test_bare_secrets_still_work(self, monkeypatch, test_session):
        """Existing deployments configured before names existed must keep
        working across an upgrade."""
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "legacy-key-1,legacy-key-2")
        result = await require_api_key(api_key="legacy-key-2", session=test_session)
        assert result.secret == "legacy-key-2"
        assert result.name == "unnamed"

    async def test_whitespace_in_config_is_tolerated(self, monkeypatch, test_session):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", " a:key-a , b:key-b ")
        result = await require_api_key(api_key="key-b", session=test_session)
        assert result.name == "b"


class TestSelfServeKeys:
    """DB-issued keys - the second tier, checked when the env-var path misses."""

    async def test_valid_self_serve_key_is_accepted(self, monkeypatch, test_session):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "admin:admin-secret")
        plaintext = await _create_user_and_key(test_session, name="predify")

        result = await require_api_key(api_key=plaintext, session=test_session)
        assert result.name == "predify"

    async def test_revoked_self_serve_key_is_rejected(self, monkeypatch, test_session):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "admin:admin-secret")
        plaintext, _, hashed = generate_secret()
        user = User(firebase_uid="uid-revoked", email="revoked@example.com")
        test_session.add(user)
        await test_session.commit()
        await test_session.refresh(user)

        from app.utils.datetime_utils import utcnow

        record = ApiKeyRecord(
            owner_user_id=user.id,
            name="revoked",
            key_prefix=plaintext[:14],
            hashed_secret=hashed,
            requests_per_minute=60,
            revoked_at=utcnow(),
        )
        test_session.add(record)
        await test_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(api_key=plaintext, session=test_session)
        assert exc_info.value.status_code == 401

    async def test_env_keys_are_checked_before_the_db(self, monkeypatch, test_session):
        """An env-configured key must keep working even if a self-serve row
        happens to exist - the two tiers don't interfere with each other."""
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "admin:admin-secret")
        await _create_user_and_key(test_session)

        result = await require_api_key(api_key="admin-secret", session=test_session)
        assert result.name == "admin"

    async def test_two_customers_naming_a_key_the_same_thing_do_not_share_a_bucket(
        self, monkeypatch, test_session
    ):
        """The rate-limiter-keying fix this tier requires: two different
        self-serve customers can both call a key 'predify' without starving
        each other, because they're bucketed by record id, not name."""
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "")
        monkeypatch.setattr(settings, "GATEWAY_ALLOW_ANONYMOUS", False)

        key_a = await _create_user_and_key(
            test_session, name="predify", requests_per_minute=1
        )
        key_b = await _create_user_and_key(
            test_session, name="predify", requests_per_minute=1
        )

        await require_api_key(api_key=key_a, session=test_session)
        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(api_key=key_a, session=test_session)
        assert exc_info.value.status_code == 429

        # key_b is a different customer entirely and must be unaffected.
        result = await require_api_key(api_key=key_b, session=test_session)
        assert result.name == "predify"


class TestRateLimiting:
    async def test_key_is_limited_at_its_configured_rate(self, monkeypatch, test_session):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "small:secret:3")

        for _ in range(3):
            await require_api_key(api_key="secret", session=test_session)

        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(api_key="secret", session=test_session)

        assert exc_info.value.status_code == 429
        assert exc_info.value.headers["Retry-After"]

    async def test_one_consumer_cannot_exhaust_another(self, monkeypatch, test_session):
        """The whole point: a runaway client must not starve everyone else,
        including the sync jobs sharing this process."""
        monkeypatch.setattr(
            settings, "GATEWAY_API_KEYS", "noisy:secret-a:2,quiet:secret-b:2"
        )

        for _ in range(2):
            await require_api_key(api_key="secret-a", session=test_session)
        with pytest.raises(HTTPException):
            await require_api_key(api_key="secret-a", session=test_session)

        # Unaffected.
        result = await require_api_key(api_key="secret-b", session=test_session)
        assert result.name == "quiet"

    async def test_keys_without_their_own_limit_use_the_default(
        self, monkeypatch, test_session
    ):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "plain:secret")
        monkeypatch.setattr(settings, "DEFAULT_RATE_LIMIT_PER_MINUTE", 2)

        for _ in range(2):
            await require_api_key(api_key="secret", session=test_session)
        with pytest.raises(HTTPException) as exc_info:
            await require_api_key(api_key="secret", session=test_session)
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

    def test_rate_limit_key_defaults_to_name(self):
        [key] = parse_api_keys("predify:s3cret", default_rpm=60)
        assert key.rate_limit_key == "predify"


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
