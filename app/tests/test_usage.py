"""Per-key usage metering - app.core.usage.record_usage and its wiring
into require_api_key.
"""

import pytest
from sqlmodel import select

from app.core.auth import require_api_key
from app.core.config import settings
from app.core.usage import record_usage
from app.db.models.api_key_usage import ApiKeyUsageDaily, ApiKeyUsageHourly

pytestmark = pytest.mark.asyncio


class TestRecordUsage:
    async def test_creates_a_daily_and_hourly_row_on_first_use(self, test_session):
        await record_usage(test_session, "some-key")

        daily = (await test_session.exec(select(ApiKeyUsageDaily))).all()
        hourly = (await test_session.exec(select(ApiKeyUsageHourly))).all()
        assert len(daily) == 1
        assert len(hourly) == 1
        assert daily[0].request_count == 1
        assert hourly[0].request_count == 1

    async def test_increments_existing_rows_on_repeat_use(self, test_session):
        for _ in range(3):
            await record_usage(test_session, "some-key")

        daily = (await test_session.exec(select(ApiKeyUsageDaily))).all()
        hourly = (await test_session.exec(select(ApiKeyUsageHourly))).all()
        assert len(daily) == 1
        assert len(hourly) == 1
        assert daily[0].request_count == 3
        assert hourly[0].request_count == 3

    async def test_different_keys_get_separate_counters(self, test_session):
        await record_usage(test_session, "key-a")
        await record_usage(test_session, "key-b")
        await record_usage(test_session, "key-a")

        rows = {
            row.rate_limit_key: row.request_count
            for row in (await test_session.exec(select(ApiKeyUsageDaily))).all()
        }
        assert rows == {"key-a": 2, "key-b": 1}

    async def test_a_failure_is_swallowed_not_raised(self, test_session, monkeypatch):
        """Metering must never take the request down with it."""

        async def _boom(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(test_session, "exec", _boom)
        await record_usage(test_session, "some-key")  # must not raise


class TestWiredIntoAuth:
    async def test_a_real_request_is_metered(self, monkeypatch, test_session):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "ops:secret")
        await require_api_key(api_key="secret", session=test_session)

        rows = (await test_session.exec(select(ApiKeyUsageDaily))).all()
        assert len(rows) == 1
        assert rows[0].rate_limit_key == "ops"
        assert rows[0].request_count == 1

    async def test_anonymous_requests_are_not_metered(self, monkeypatch, test_session):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "")
        monkeypatch.setattr(settings, "GATEWAY_ALLOW_ANONYMOUS", True)
        await require_api_key(api_key=None, session=test_session)

        rows = (await test_session.exec(select(ApiKeyUsageDaily))).all()
        assert rows == []

    async def test_rejected_requests_are_not_metered(self, monkeypatch, test_session):
        monkeypatch.setattr(settings, "GATEWAY_API_KEYS", "ops:secret")
        with pytest.raises(Exception):
            await require_api_key(api_key="wrong-secret", session=test_session)

        rows = (await test_session.exec(select(ApiKeyUsageDaily))).all()
        assert rows == []
