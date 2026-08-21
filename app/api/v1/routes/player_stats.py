from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import require_api_key
from app.db.database import get_session
from app.db.models import League, PlayerStat, Team
from app.schemas.player_stat import PlayerStatListResponse, PlayerStatOut

router = APIRouter(prefix="/leagues/{league_id}/players", tags=["players"])


@router.get("", response_model=PlayerStatListResponse)
async def list_player_stats(
    league_id: int,
    season: Optional[int] = Query(
        None, description="Defaults to the league's current season"
    ),
    team_id: Optional[List[int]] = Query(
        None, description="Filter to one or more team IDs, e.g. for a head-to-head pick"
    ),
    limit: int = Query(50, le=100),
    session: AsyncSession = Depends(get_session),
    _: str = Depends(require_api_key),
):
    league = await session.get(League, league_id)
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    season_year = season or league.current_season_year
    if not season_year:
        return PlayerStatListResponse(items=[], total=0)

    # Team's current league, not season-scoped - see Team's docstring.
    team_rows = (
        await session.exec(select(Team.id).where(Team.league_id == league.id))
    ).all()
    league_team_ids = set(team_rows)
    target_team_ids = league_team_ids & set(team_id) if team_id else league_team_ids
    if not target_team_ids:
        return PlayerStatListResponse(items=[], total=0)

    query = (
        select(PlayerStat)
        .where(
            PlayerStat.team_id.in_(target_team_ids),
            PlayerStat.season_year == season_year,
        )
        .order_by(PlayerStat.goals.desc(), PlayerStat.assists.desc())
        .limit(limit)
    )
    rows = (await session.exec(query)).all()

    items = [PlayerStatOut.model_validate(row) for row in rows]
    return PlayerStatListResponse(items=items, total=len(items))
