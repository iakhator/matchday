from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import require_api_key
from app.db.database import get_session
from app.db.models import League, Team
from app.schemas.team import TeamOut

router = APIRouter(prefix="/leagues/{league_id}/teams", tags=["teams"])


@router.get("", response_model=List[TeamOut])
async def list_teams(
    league_id: str,
    season: Optional[int] = Query(
        None, description="Defaults to the league's current season"
    ),
    session: AsyncSession = Depends(get_session),
    _: str = Depends(require_api_key),
):
    league = await session.get(League, league_id)
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    season_year = season or league.current_season_year
    if not season_year:
        return []

    teams = (
        await session.exec(
            select(Team).where(
                Team.league_id == league.id, Team.season_year == season_year
            )
        )
    ).all()
    return teams
