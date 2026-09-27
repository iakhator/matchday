from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.api_keys import ApiKey
from app.core.auth import require_api_key
from app.db.database import get_session
from app.db.models import Fixture, League, Standing
from app.schemas.league import LeagueOut

router = APIRouter(prefix="/leagues", tags=["leagues"])


@router.get("", response_model=List[LeagueOut])
async def list_leagues(
    country: Optional[str] = Query(
        None, description="Case-insensitive exact match"
    ),
    session: AsyncSession = Depends(get_session),
    _: ApiKey = Depends(require_api_key),
):
    query = select(League)
    if country is not None:
        query = query.where(func.lower(League.country) == country.lower())

    leagues = (await session.exec(query)).all()
    return leagues


@router.get("/{league_id}", response_model=LeagueOut)
async def get_league(
    league_id: int,
    session: AsyncSession = Depends(get_session),
    _: ApiKey = Depends(require_api_key),
):
    league = await session.get(League, league_id)
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    return league


@router.get("/{league_id}/seasons", response_model=List[int])
async def list_league_seasons(
    league_id: int,
    session: AsyncSession = Depends(get_session),
    _: ApiKey = Depends(require_api_key),
):
    """Which season years this league actually has data for, most recent
    first - so a consumer can build a season picker without guessing years
    or hitting /fixtures blind. Unioned across fixtures and standings since
    one can sync slightly ahead of the other for a brand-new season."""
    league = await session.get(League, league_id)
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    fixture_years = await session.exec(
        select(Fixture.season_year)
        .where(Fixture.league_id == league_id)
        .distinct()
    )
    standing_years = await session.exec(
        select(Standing.season_year)
        .where(Standing.league_id == league_id)
        .distinct()
    )

    years = set(fixture_years.all()) | set(standing_years.all())
    return sorted(years, reverse=True)
