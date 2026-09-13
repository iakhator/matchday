from app.core.heartbeat import record_heartbeat
from app.core.logger import logger
from app.core.scheduler_config import SchedulerConfig
from app.db.database import async_session
from app.services.sync_service import SyncService
from app.utils.datetime_utils import utcnow


async def sync_leagues_and_teams_job() -> None:
    """Slow-cadence job: refresh league metadata + current season's team
    roster for every tracked competition."""
    synced = 0
    async with async_session() as session:
        sync_service = SyncService(session)
        for code in SchedulerConfig.TRACKED_COMPETITIONS:
            try:
                league = await sync_service.sync_league(code)
                if league.current_season_year:
                    await sync_service.sync_teams(league, league.current_season_year)
                synced += 1
            except Exception:
                logger.exception(f"League/team sync failed for '{code}'")
        # Only a heartbeat if at least one competition actually synced -
        # an upstream/connector outage that fails every competition every
        # run should go stale and alert, not look healthy just because
        # the job function itself didn't crash. See app/core/heartbeat.py.
        if synced:
            await record_heartbeat(session, "sync_leagues_and_teams")


async def sync_fixtures_job() -> None:
    """Frequent-cadence job: refresh fixtures/scores for every tracked
    competition's current season. This is the job that keeps postponements,
    reschedules and results flowing continuously."""
    synced = 0
    async with async_session() as session:
        sync_service = SyncService(session)
        for code in SchedulerConfig.TRACKED_COMPETITIONS:
            try:
                league = await sync_service.sync_league(code)
                if league.current_season_year:
                    await sync_service.sync_fixtures(
                        league, league.current_season_year
                    )
                synced += 1
            except Exception:
                logger.exception(f"Fixture sync failed for '{code}'")
        if synced:
            await record_heartbeat(session, "sync_fixtures")


async def sync_standings_and_players_job() -> None:
    """Medium-cadence job: refresh league tables and season scorer stats for
    every tracked competition's current season."""
    synced = 0
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
                synced += 1
            except Exception:
                logger.exception(f"Standings/player stats sync failed for '{code}'")
        if synced:
            await record_heartbeat(session, "sync_standings_and_players")


async def sync_live_fixtures_job() -> None:
    """Fast-cadence job: keeps scores fresh during an actual match instead
    of waiting for the next 15-minute cycle. Only calls the upstream API
    for competitions that currently have a fixture in its live window
    (see SyncService.has_live_window_fixtures) - a plain DB check, so this
    runs every tick at zero upstream cost when nothing's on."""
    async with async_session() as session:
        sync_service = SyncService(session)
        checked_ok = True
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
                checked_ok = False
        # Unlike the other jobs, "nothing was live" is a normal, successful
        # outcome here (that's the whole point of the cheap DB check) - so
        # the heartbeat fires as long as the DB check itself didn't blow up,
        # not just when an upstream sync actually happened.
        if checked_ok:
            await record_heartbeat(session, "sync_live_fixtures")


async def map_api_football_fixtures_job() -> None:
    """Daily: match api-football's fixture ids onto the ones we hold.

    Two dates, today and tomorrow. Mapping has to happen *before* anything
    needs it - odds are wanted a day ahead of kickoff, and a fixture mapped
    after its match has started can never have odds at all.

    Two requests out of a 100/day budget. One call covers every competition
    api-football knows about, so this does not grow with our coverage.
    """
    from datetime import timedelta

    from app.connectors.api_football import ApiFootballConnector, DailyBudgetExceeded
    from app.services.fixture_mapper import FixtureMapper

    mapped, succeeded = 0, 0
    async with async_session() as session:
        try:
            connector = ApiFootballConnector()
        except RuntimeError as exc:
            # No key configured. A gateway running on football-data.org
            # alone is a valid deployment, so this is a note, not an error.
            logger.info(f"Skipping api-football mapping: {exc}")
            return

        mapper = FixtureMapper(session, connector)
        today = utcnow().date()
        for day in (today, today + timedelta(days=1)):
            try:
                mapped += len(await mapper.map_date(day))
                succeeded += 1
            except DailyBudgetExceeded as exc:
                logger.error(f"Fixture mapping stopped: {exc}")
                break
            except Exception:
                logger.exception(f"Fixture mapping failed for {day}")

        # Heartbeat only if a date was actually processed. Zero new
        # mappings is a success - a quiet Tuesday maps nothing - but zero
        # *successful calls* is a failure, and stamping regardless would
        # report healthy while the job did nothing at all. Same rule the
        # other jobs here follow, and it was worth following: an early
        # version stamped unconditionally and looked fine through a run
        # where every request failed DNS.
        if succeeded:
            await record_heartbeat(session, "map_api_football_fixtures")
    if mapped:
        logger.info(f"Mapped {mapped} api-football fixtures")


async def capture_odds_job() -> None:
    """Hourly: capture pre-match odds for fixtures kicking off soon.

    The only job here with a deadline. Odds cannot be fetched after
    kickoff, so a window missed is a hole nothing later can fill - hourly
    gives roughly 24 attempts inside the 24-hour capture window, so a few
    failed runs are survivable.
    """
    from app.connectors.api_football import ApiFootballConnector
    from app.services.odds_service import OddsService

    async with async_session() as session:
        try:
            connector = ApiFootballConnector()
        except RuntimeError as exc:
            logger.info(f"Skipping odds capture: {exc}")
            return

        try:
            await OddsService(session, connector).capture_upcoming()
        except Exception:
            # Deliberately swallowed after logging: a failure here must not
            # take down the scheduler and with it the fixture sync, which
            # is the more important of the two.
            logger.exception("Odds capture failed")
            return

        await record_heartbeat(session, "capture_odds")
