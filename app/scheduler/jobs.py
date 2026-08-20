from app.core.logger import logger
from app.core.scheduler_config import SchedulerConfig
from app.db.database import async_session
from app.services.sync_service import SyncService


async def sync_leagues_and_teams_job() -> None:
    """Slow-cadence job: refresh league metadata + current season's team
    roster for every tracked competition."""
    async with async_session() as session:
        sync_service = SyncService(session)
        for code in SchedulerConfig.TRACKED_COMPETITIONS:
            try:
                league = await sync_service.sync_league(code)
                if league.current_season_year:
                    await sync_service.sync_teams(league, league.current_season_year)
            except Exception:
                logger.exception(f"League/team sync failed for '{code}'")


async def sync_fixtures_job() -> None:
    """Frequent-cadence job: refresh fixtures/scores for every tracked
    competition's current season. This is the job that keeps postponements,
    reschedules and results flowing continuously."""
    async with async_session() as session:
        sync_service = SyncService(session)
        for code in SchedulerConfig.TRACKED_COMPETITIONS:
            try:
                league = await sync_service.sync_league(code)
                if league.current_season_year:
                    await sync_service.sync_fixtures(
                        league, league.current_season_year
                    )
            except Exception:
                logger.exception(f"Fixture sync failed for '{code}'")


async def sync_standings_and_players_job() -> None:
    """Medium-cadence job: refresh league tables and season scorer stats for
    every tracked competition's current season."""
    async with async_session() as session:
        sync_service = SyncService(session)
        for code in SchedulerConfig.TRACKED_COMPETITIONS:
            try:
                league = await sync_service.sync_league(code)
                if league.current_season_year:
                    await sync_service.sync_standings(
                        league, league.current_season_year
                    )
                    await sync_service.sync_player_stats(
                        league, league.current_season_year
                    )
            except Exception:
                logger.exception(f"Standings/player stats sync failed for '{code}'")


async def sync_live_fixtures_job() -> None:
    """Fast-cadence job: keeps scores fresh during an actual match instead
    of waiting for the next 15-minute cycle. Only calls the upstream API
    for competitions that currently have a fixture in its live window
    (see SyncService.has_live_window_fixtures) - a plain DB check, so this
    runs every tick at zero upstream cost when nothing's on."""
    async with async_session() as session:
        sync_service = SyncService(session)
        for code in SchedulerConfig.TRACKED_COMPETITIONS:
            try:
                if not await sync_service.has_live_window_fixtures(code):
                    continue
                league = await sync_service.sync_league(code)
                if league.current_season_year:
                    await sync_service.sync_fixtures(
                        league, league.current_season_year
                    )
            except Exception:
                logger.exception(f"Live fixture sync failed for '{code}'")
