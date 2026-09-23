from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.api_keys import (
    ANONYMOUS,
    ApiKey,
    find_db_key,
    find_key,
    has_any_db_keys,
    parse_api_keys,
)
from app.core.config import settings
from app.core.rate_limit import limiter
from app.db.database import get_session

api_key_header = APIKeyHeader(name="X-Gateway-Key", auto_error=False)


async def require_api_key(
    api_key: str = Security(api_key_header),
    session: AsyncSession = Depends(get_session),
) -> ApiKey:
    """Identify the caller and hold them to their rate limit.

    Returns the matched key rather than a bare string so callers and logs
    can refer to a consumer by name instead of by secret.

    Two tiers, checked in order: env-configured keys (GATEWAY_API_KEYS -
    admin/service consumers an operator curates by hand) first, then
    self-serve DB-issued keys. Every route stays written against this one
    `ApiKey` contract regardless of which tier actually matched.

    Note this fails *closed*. With no keys configured anywhere and no
    explicit opt-out, every request is refused. The previous behaviour was
    to disable auth entirely when the list was empty, which meant a
    deployment that simply forgot to set it served everything to anyone,
    quietly and indefinitely. Refusing is loud, and the error says exactly
    which setting fixes it.
    """
    keys = parse_api_keys(
        settings.GATEWAY_API_KEYS, settings.DEFAULT_RATE_LIMIT_PER_MINUTE
    )

    if not keys and not await has_any_db_keys(session):
        if settings.GATEWAY_ALLOW_ANONYMOUS:
            return ANONYMOUS
        raise HTTPException(
            status_code=503,
            detail=(
                "This gateway has no API keys configured. Set GATEWAY_API_KEYS "
                "(for example 'myapp:some-secret'), or set "
                "GATEWAY_ALLOW_ANONYMOUS=true to run without auth in local "
                "development."
            ),
        )

    matched = find_key(keys, api_key) or await find_db_key(session, api_key)
    if not matched:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Gateway-Key")

    # Keyed by rate_limit_key rather than name: env keys use their name (one
    # operator curates every name, so collisions can't happen by accident),
    # self-serve keys use their own record id (two different customers could
    # otherwise both call a key "predify" and share one bucket). Either way,
    # rotating a secret under the same identity does not hand out a fresh
    # allowance mid-minute.
    retry_after = limiter.check(matched.rate_limit_key, matched.requests_per_minute)
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Rate limit exceeded for '{matched.name}' "
                f"({matched.requests_per_minute} requests/minute)"
            ),
            headers={"Retry-After": str(retry_after)},
        )

    return matched
