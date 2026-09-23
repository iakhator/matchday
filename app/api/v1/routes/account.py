import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.api_keys import generate_secret
from app.core.config import settings
from app.core.user_auth import require_firebase_user
from app.db.database import get_session
from app.db.models.api_key import ApiKeyRecord
from app.db.models.user import User
from app.schemas.api_key import (
    ApiKeyCreatedOut,
    ApiKeyCreateRequest,
    ApiKeyListResponse,
    ApiKeyOut,
)
from app.utils.datetime_utils import utcnow

router = APIRouter(prefix="/account", tags=["account"])


async def _owned_live_keys(session: AsyncSession, user: User) -> list[ApiKeyRecord]:
    return list(
        (
            await session.exec(
                select(ApiKeyRecord).where(
                    ApiKeyRecord.owner_user_id == user.id,
                    ApiKeyRecord.revoked_at.is_(None),
                )
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
    """Every key this account has ever generated, revoked or not - the
    secret itself is never included, only `key_prefix`."""
    rows = (
        await session.exec(
            select(ApiKeyRecord)
            .where(ApiKeyRecord.owner_user_id == user.id)
            .order_by(ApiKeyRecord.created_at.desc())
        )
    ).all()
    items = [ApiKeyOut.model_validate(row) for row in rows]
    return ApiKeyListResponse(items=items, total=len(items))


@router.delete("/keys/{key_id}", response_model=ApiKeyOut)
async def revoke_key(
    key_id: uuid.UUID,
    user: User = Depends(require_firebase_user),
    session: AsyncSession = Depends(get_session),
):
    """Revocation is a timestamp, not a delete - see ApiKeyRecord's
    docstring for why. Scoped to owner_user_id so one account can never
    revoke another's key, including by guessing an id."""
    record = (
        await session.exec(
            select(ApiKeyRecord).where(
                ApiKeyRecord.id == key_id, ApiKeyRecord.owner_user_id == user.id
            )
        )
    ).first()
    if record is None:
        raise HTTPException(status_code=404, detail="API key not found")

    if record.revoked_at is None:
        record.revoked_at = utcnow()
        session.add(record)
        await session.commit()
        await session.refresh(record)

    return record


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

    if old.revoked_at is None:
        old.revoked_at = utcnow()
        session.add(old)

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
