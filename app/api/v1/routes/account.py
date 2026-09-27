import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.api_keys import generate_secret
from app.core.config import settings
from app.core.user_auth import require_firebase_user
from app.db.database import get_session
from app.db.models.api_key import ApiKeyRecord
from app.db.models.api_key_usage import ApiKeyUsageDaily, ApiKeyUsageHourly
from app.db.models.user import User
from app.schemas.api_key import (
    ApiKeyCreatedOut,
    ApiKeyCreateRequest,
    ApiKeyListResponse,
    ApiKeyOut,
)
from app.schemas.usage import HourlyUsageOut, KeyUsageOut, UsageResponse
from app.utils.datetime_utils import ensure_utc, utcnow

HOURLY_WINDOW_HOURS = 24

router = APIRouter(prefix="/account", tags=["account"])


async def _owned_live_keys(session: AsyncSession, user: User) -> list[ApiKeyRecord]:
    """Every key this account owns. All of them are live - a revoked key's
    row is deleted, not flagged, so a row existing at all means it works."""
    return list(
        (
            await session.exec(
                select(ApiKeyRecord).where(ApiKeyRecord.owner_user_id == user.id)
            )
        ).all()
    )


@router.post("/keys", response_model=ApiKeyCreatedOut)
async def create_key(
    body: ApiKeyCreateRequest,
    user: User = Depends(require_firebase_user),
    session: AsyncSession = Depends(get_session),
):
    """Generates a new self-serve key. The plaintext secret in this
    response is the only time it is ever shown - store it now."""
    live_keys = await _owned_live_keys(session, user)
    if len(live_keys) >= settings.MAX_API_KEYS_PER_USER:
        raise HTTPException(
            status_code=422,
            detail=(
                f"You already have {len(live_keys)} active keys, the "
                f"maximum allowed ({settings.MAX_API_KEYS_PER_USER}). "
                "Revoke one before generating another."
            ),
        )

    plaintext, prefix, hashed = generate_secret()
    record = ApiKeyRecord(
        owner_user_id=user.id,
        name=body.name,
        key_prefix=prefix,
        hashed_secret=hashed,
        requests_per_minute=settings.SELF_SERVE_RATE_LIMIT_PER_MINUTE,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)

    return ApiKeyCreatedOut(
        id=record.id,
        name=record.name,
        key_prefix=record.key_prefix,
        secret=plaintext,
        requests_per_minute=record.requests_per_minute,
        created_at=record.created_at,
    )


@router.get("/keys", response_model=ApiKeyListResponse)
async def list_keys(
    user: User = Depends(require_firebase_user),
    session: AsyncSession = Depends(get_session),
):
    """Every key this account currently owns - a revoked key's row is
    deleted, so nothing but live keys ever appears here. The secret itself
    is never included, only `key_prefix`."""
    rows = (
        await session.exec(
            select(ApiKeyRecord)
            .where(ApiKeyRecord.owner_user_id == user.id)
            .order_by(ApiKeyRecord.created_at.desc())
        )
    ).all()
    items = [ApiKeyOut.model_validate(row) for row in rows]
    return ApiKeyListResponse(items=items, total=len(items))


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    user: User = Depends(require_firebase_user),
    session: AsyncSession = Depends(get_session),
):
    """Today's and this month's request count for every key this account
    owns, plus an hourly series for the last 24 hours - people will not
    trust a limit or a bill they cannot check against their own numbers,
    and a rollup alone can't explain a burst that tripped a 429."""
    keys = await _owned_live_keys(session, user)
    now = utcnow()
    current_hour = now.replace(minute=0, second=0, microsecond=0)
    window_start = current_hour - timedelta(hours=HOURLY_WINDOW_HOURS - 1)
    today = now.date()
    month_start = today.replace(day=1)

    items = []
    for key in keys:
        rate_limit_key = str(key.id)

        daily_rows = (
            await session.exec(
                select(ApiKeyUsageDaily).where(
                    ApiKeyUsageDaily.rate_limit_key == rate_limit_key,
                    ApiKeyUsageDaily.date >= month_start,
                )
            )
        ).all()

        hourly_rows = (
            await session.exec(
                select(ApiKeyUsageHourly).where(
                    ApiKeyUsageHourly.rate_limit_key == rate_limit_key,
                    ApiKeyUsageHourly.hour >= window_start,
                )
            )
        ).all()
        # Normalized to UTC before keying the dict - SQLite (tests) doesn't
        # round-trip a timezone-aware datetime the same way Postgres does.
        counts_by_hour = {
            ensure_utc(row.hour): row.request_count for row in hourly_rows
        }
        # Zero-filled so the chart gets a continuous 24-point series rather
        # than gaps wherever an hour had no traffic.
        hourly = [
            HourlyUsageOut(
                hour=window_start + timedelta(hours=i),
                count=counts_by_hour.get(window_start + timedelta(hours=i), 0),
            )
            for i in range(HOURLY_WINDOW_HOURS)
        ]

        items.append(
            KeyUsageOut(
                key_id=key.id,
                name=key.name,
                requests_today=sum(
                    r.request_count for r in daily_rows if r.date == today
                ),
                requests_this_month=sum(r.request_count for r in daily_rows),
                hourly=hourly,
            )
        )

    return UsageResponse(items=items)


@router.delete("/keys/{key_id}", response_model=ApiKeyOut)
async def revoke_key(
    key_id: uuid.UUID,
    user: User = Depends(require_firebase_user),
    session: AsyncSession = Depends(get_session),
):
    """Revocation deletes the row - see ApiKeyRecord's docstring for why.
    Scoped to owner_user_id so one account can never revoke another's key,
    including by guessing an id."""
    record = (
        await session.exec(
            select(ApiKeyRecord).where(
                ApiKeyRecord.id == key_id, ApiKeyRecord.owner_user_id == user.id
            )
        )
    ).first()
    if record is None:
        raise HTTPException(status_code=404, detail="API key not found")

    # Read the response out before deleting - the ORM instance can't be
    # refreshed from a row that no longer exists.
    result = ApiKeyOut.model_validate(record)
    await session.delete(record)
    await session.commit()

    return result


@router.post("/keys/{key_id}/rotate", response_model=ApiKeyCreatedOut)
async def rotate_key(
    key_id: uuid.UUID,
    user: User = Depends(require_firebase_user),
    session: AsyncSession = Depends(get_session),
):
    """Revoke the old key and generate its replacement in one request,
    carrying over its name and rate limit. Same safety property as
    create_key - the plaintext is shown exactly once, here - just without
    making the caller do it as two separate manual steps.

    Doesn't touch MAX_API_KEYS_PER_USER: the old key stops counting as
    live in the same commit the new one starts counting, so the live
    count this account holds never changes because of a rotation.
    """
    old = (
        await session.exec(
            select(ApiKeyRecord).where(
                ApiKeyRecord.id == key_id, ApiKeyRecord.owner_user_id == user.id
            )
        )
    ).first()
    if old is None:
        raise HTTPException(status_code=404, detail="API key not found")

    await session.delete(old)

    plaintext, prefix, hashed = generate_secret()
    new_record = ApiKeyRecord(
        owner_user_id=user.id,
        name=old.name,
        key_prefix=prefix,
        hashed_secret=hashed,
        requests_per_minute=old.requests_per_minute,
    )
    session.add(new_record)
    await session.commit()
    await session.refresh(new_record)

    return ApiKeyCreatedOut(
        id=new_record.id,
        name=new_record.name,
        key_prefix=new_record.key_prefix,
        secret=plaintext,
        requests_per_minute=new_record.requests_per_minute,
        created_at=new_record.created_at,
    )
