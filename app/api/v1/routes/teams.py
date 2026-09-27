from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.api_keys import ApiKey
from app.core.auth import require_api_key
from app.db.database import get_session
from app.db.models import League, Team
from app.schemas.team import TeamOut

router = APIRouter(tags=["teams"])


@router.get("/leagues/{league_id}/teams", response_model=List[TeamOut])
async def list_teams(
    league_id: int,
    session: AsyncSession = Depends(get_session),
    _: ApiKey = Depends(require_api_key),
):
    """Always the *current* roster - Team rows aren't season-scoped (a
    club keeps the same id forever, see the Team model's docstring), so
    there's no way to ask for a past season's roster here. For historical
    per-season data, use /standings instead."""
    league = await session.get(League, league_id)
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    teams = (
        await session.exec(select(Team).where(Team.league_id == league.id))
    ).all()
    return teams


@router.get("/teams/{team_id}", response_model=TeamOut)
async def get_team(
    team_id: int,
    session: AsyncSession = Depends(get_session),
    _: ApiKey = Depends(require_api_key),
):
    """Direct lookup by the id this gateway already hands out - in
    fixtures, standings and lookup responses - without needing to know
    which league the team belongs to first."""
    team = await session.get(Team, team_id)
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team
