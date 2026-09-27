from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.api_keys import ApiKey
from app.core.auth import require_api_key
from app.core.pagination import Pagination, pagination_params
from app.db.database import get_session
from app.db.models import League, Standing, Team
from app.schemas.standing import StandingListResponse, StandingOut
from app.schemas.team import TeamOut

router = APIRouter(prefix="/leagues/{league_id}/standings", tags=["standings"])


@router.get("", response_model=StandingListResponse)
async def list_standings(
    league_id: int,
    season: Optional[int] = Query(
        None, description="Defaults to the league's current season"
    ),
    page: Pagination = Depends(pagination_params),
    session: AsyncSession = Depends(get_session),
    _: ApiKey = Depends(require_api_key),
):
    league = await session.get(League, league_id)
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    season_year = season or league.current_season_year
    if not season_year:
        return StandingListResponse(items=[], total=0)

    conditions = (Standing.league_id == league.id, Standing.season_year == season_year)

    total = (
        await session.exec(
            select(func.count()).select_from(Standing).where(*conditions)
        )
    ).one()

    query = (
        select(Standing, Team)
        .join(Team, Team.id == Standing.team_id)
        .where(*conditions)
        .order_by(Standing.rank)
        .offset(page.offset)
        .limit(page.limit)
    )
    rows = (await session.exec(query)).all()

    items = [
        StandingOut(
            id=standing.id,
            league_id=standing.league_id,
            season_year=standing.season_year,
            team=TeamOut.model_validate(team),
            rank=standing.rank,
            points=standing.points,
            played=standing.played,
            won=standing.won,
            drawn=standing.drawn,
            lost=standing.lost,
            goals_for=standing.goals_for,
            goals_against=standing.goals_against,
            form=standing.form,
            last_synced_at=standing.last_synced_at,
        )
        for standing, team in rows
    ]

    return StandingListResponse(items=items, total=total)
