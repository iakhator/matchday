from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import require_api_key
from app.db.database import get_session
from app.db.models import League
from app.schemas.league import LeagueOut

router = APIRouter(prefix="/leagues", tags=["leagues"])


@router.get("", response_model=List[LeagueOut])
async def list_leagues(
    session: AsyncSession = Depends(get_session),
    _: str = Depends(require_api_key),
):
    leagues = (await session.exec(select(League))).all()
    return leagues


@router.get("/{league_id}", response_model=LeagueOut)
async def get_league(
    league_id: str,
    session: AsyncSession = Depends(get_session),
    _: str = Depends(require_api_key),
):
    league = await session.get(League, league_id)
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    return league
