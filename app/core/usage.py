"""Per-key request metering - see ApiKeyUsageDaily/ApiKeyUsageHourly for
why these are counters rather than a raw per-request log.
"""

from typing import Type, TypeVar

from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logger import logger
from app.db.models.api_key_usage import ApiKeyUsageDaily, ApiKeyUsageHourly
from app.utils.datetime_utils import utcnow

ModelT = TypeVar("ModelT", ApiKeyUsageDaily, ApiKeyUsageHourly)


async def _increment(
    session: AsyncSession,
    model: Type[ModelT],
    bucket_field: str,
    bucket_value,
    rate_limit_key: str,
) -> None:
    """Increment the counter for one (rate_limit_key, bucket) row, creating
    it on first use. A rare race between the SELECT-miss and the INSERT
    (two requests for the same brand-new key/bucket) falls back to an
    UPDATE rather than losing one request's count."""
    row = (
        await session.exec(
            select(model).where(
                model.rate_limit_key == rate_limit_key,
                getattr(model, bucket_field) == bucket_value,
            )
        )
    ).first()
    if row is not None:
        row.request_count += 1
        session.add(row)
        await session.commit()
        return

    session.add(
        model(
            rate_limit_key=rate_limit_key,
            request_count=1,
            **{bucket_field: bucket_value},
        )
    )
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        row = (
            await session.exec(
                select(model).where(
                    model.rate_limit_key == rate_limit_key,
                    getattr(model, bucket_field) == bucket_value,
                )
            )
        ).first()
        if row is not None:
            row.request_count += 1
            session.add(row)
            await session.commit()


async def record_usage(session: AsyncSession, rate_limit_key: str) -> None:
    """Increment today's daily counter and this hour's hourly counter for
    this key.

    Never allowed to break the request it's metering - a usage-tracking
    bug should not turn into an outage for every authenticated call, so
    any failure here is logged and swallowed.
    """
    now = utcnow()
    hour = now.replace(minute=0, second=0, microsecond=0)
    try:
        await _increment(session, ApiKeyUsageDaily, "date", now.date(), rate_limit_key)
        await _increment(session, ApiKeyUsageHourly, "hour", hour, rate_limit_key)
    except Exception:
        logger.exception(f"Failed to record usage for key '{rate_limit_key}'")
        await session.rollback()
