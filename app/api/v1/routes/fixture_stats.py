from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import require_api_key
from app.db.database import get_session
from app.db.models import Fixture, PlayerMatchStat, ShotEvent, TeamMatchStat
from app.schemas.player_match_stat import (
    PlayerMatchStatListResponse,
    PlayerMatchStatOut,
)
from app.schemas.shot_event import ShotEventListResponse, ShotEventOut
from app.schemas.team_match_stat import TeamMatchStatListResponse, TeamMatchStatOut

router = APIRouter(prefix="/fixtures/{fixture_id}", tags=["fixture-stats"])


async def _require_fixture(fixture_id: int, session: AsyncSession) -> Fixture:
    fixture = await session.get(Fixture, fixture_id)
    if not fixture:
        raise HTTPException(status_code=404, detail="Fixture not found")
    return fixture


@router.get("/player-stats", response_model=PlayerMatchStatListResponse)
async def list_player_match_stats(
    fixture_id: int,
    session: AsyncSession = Depends(get_session),
    _: str = Depends(require_api_key),
):
    """Advanced per-player match stats (xG, xA, xG-chain/buildup) from
    Understat. Empty if ENABLE_SOCCERDATA is off or Understat has no data
    for this fixture yet (only populated post-match)."""
    await _require_fixture(fixture_id, session)
    rows = (
        await session.exec(
            select(PlayerMatchStat)
            .where(PlayerMatchStat.fixture_id == fixture_id)
            .order_by(PlayerMatchStat.xg.desc())
        )
    ).all()
    items = [PlayerMatchStatOut.model_validate(row) for row in rows]
    return PlayerMatchStatListResponse(items=items, total=len(items))


@router.get("/team-stats", response_model=TeamMatchStatListResponse)
async def list_team_match_stats(
    fixture_id: int,
    session: AsyncSession = Depends(get_session),
    _: str = Depends(require_api_key),
):
    """Advanced team match stats (non-penalty xG, PPDA, deep completions,
    expected points) from Understat."""
    await _require_fixture(fixture_id, session)
    rows = (
        await session.exec(
            select(TeamMatchStat).where(TeamMatchStat.fixture_id == fixture_id)
        )
    ).all()
    items = [TeamMatchStatOut.model_validate(row) for row in rows]
    return TeamMatchStatListResponse(items=items, total=len(items))


@router.get("/shots", response_model=ShotEventListResponse)
async def list_shot_events(
    fixture_id: int,
    session: AsyncSession = Depends(get_session),
    _: str = Depends(require_api_key),
):
    """Shot-map data (location, xG, body part, situation, result) from
    Understat."""
    await _require_fixture(fixture_id, session)
    rows = (
        await session.exec(
            select(ShotEvent)
            .where(ShotEvent.fixture_id == fixture_id)
            .order_by(ShotEvent.minute)
        )
    ).all()
    items = [ShotEventOut.model_validate(row) for row in rows]
    return ShotEventListResponse(items=items, total=len(items))
