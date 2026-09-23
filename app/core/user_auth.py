"""Human identity for the self-serve account dashboard.

Deliberately its own module, not folded into app/core/auth.py: that file
answers "is this a valid gateway request" (X-Gateway-Key, rate limits,
data access). This answers "who is this person" (a Firebase-verified
human, managing their own account). Different header scheme on purpose -
HTTPBearer here, APIKeyHeader there - so the two can never collide on a
route that accidentally depends on both.
"""

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.firebase import verify_firebase_token
from app.db.database import get_session
from app.db.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_or_create_user(
    session: AsyncSession, firebase_uid: str, email: str
) -> User:
    """First sign-in creates the row; every sign-in after that just
    confirms it's still there. There's no separate "register" step -
    Firebase already did the actual account creation."""
    user = (
        await session.exec(select(User).where(User.firebase_uid == firebase_uid))
    ).first()
    if user is not None:
        return user

    user = User(firebase_uid=firebase_uid, email=email)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def require_firebase_user(
    credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    claims = verify_firebase_token(credentials.credentials)
    return await get_or_create_user(
        session, firebase_uid=claims["uid"], email=claims.get("email", "")
    )
