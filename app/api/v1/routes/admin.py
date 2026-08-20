from fastapi import APIRouter, Depends, HTTPException
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.auth import require_api_key
from app.core.scheduler_config import SchedulerConfig
from app.db.database import get_session
from app.services.sync_service import SyncService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/sync")
async def trigger_sync(
    session: AsyncSession = Depends(get_session),
    _: str = Depends(require_api_key),
):
    """Manually trigger a full sync of every tracked competition. Useful for
    self-hosters getting a fresh gateway populated without waiting for the
    scheduler's next tick, and for local dev/testing."""
    sync_service = SyncService(session)
    results = []

    for code in SchedulerConfig.TRACKED_COMPETITIONS:
        league = await sync_service.sync_league(code)
        teams = []
        fixtures = []
        standings = []
        player_stats = []
        if league.current_season_year:
            teams = await sync_service.sync_teams(league, league.current_season_year)
            fixtures = await sync_service.sync_fixtures(
                league, league.current_season_year
            )
            standings = await sync_service.sync_standings(
                league, league.current_season_year
            )
            player_stats = await sync_service.sync_player_stats(
                league, league.current_season_year
            )
        results.append(
            {
                "competition": code,
                "league": league.name,
                "season": league.current_season_year,
                "teams_synced": len(teams),
                "fixtures_synced": len(fixtures),
                "standings_synced": len(standings),
                "player_stats_synced": len(player_stats),
            }
        )

    return {"results": results}


@router.post("/backfill-results")
async def trigger_backfill(
    competition_code: str,
    session: AsyncSession = Depends(get_session),
    _: str = Depends(require_api_key),
):
    """Manually-triggered emergency path - never run automatically. Use
    this after football-data.org has been down, to fill in final scores
    for fixtures that were played while it was unreachable. Requires
    ENABLE_SOCCERDATA_FALLBACK=true (off by default - see README for the
    tradeoff before enabling it)."""
    sync_service = SyncService(session)
    league = await sync_service.sync_league(competition_code)
    if not league.current_season_year:
        raise HTTPException(status_code=422, detail="League has no current season")

    try:
        result = await sync_service.backfill_finished_results(
            league, league.current_season_year
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    return {"competition": competition_code, **result}
