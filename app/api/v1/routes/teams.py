from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import require_api_key
from app.db.database import get_session
from app.db.models import League, Team
from app.schemas.team import TeamOut

router = APIRouter(prefix="/leagues/{league_id}/teams", tags=["teams"])


@router.get("", response_model=List[TeamOut])
async def list_teams(
    league_id: int,
    session: AsyncSession = Depends(get_session),
    _: str = Depends(require_api_key),
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
