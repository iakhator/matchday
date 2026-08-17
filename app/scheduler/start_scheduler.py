from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.logger import logger
from app.core.scheduler_config import SchedulerConfig
from app.scheduler.jobs import (
    sync_fixtures_job,
    sync_leagues_and_teams_job,
    sync_live_fixtures_job,
)

scheduler = AsyncIOScheduler()


def start_scheduler() -> None:
    scheduler.add_job(
        sync_leagues_and_teams_job,
        # IntervalTrigger with no start_date fires once immediately, then
        # every `minutes` after - exactly what a fresh gateway needs.
        trigger=IntervalTrigger(
            minutes=SchedulerConfig.LEAGUE_TEAM_SYNC_INTERVAL_MINUTES
        ),
        id="sync_leagues_and_teams",
        replace_existing=True,
    )
    scheduler.add_job(
        sync_fixtures_job,
        trigger=IntervalTrigger(minutes=SchedulerConfig.FIXTURE_SYNC_INTERVAL_MINUTES),
        id="sync_fixtures",
        replace_existing=True,
    )
    scheduler.add_job(
        sync_live_fixtures_job,
        trigger=IntervalTrigger(seconds=SchedulerConfig.LIVE_FIXTURE_SYNC_INTERVAL_SECONDS),
        id="sync_live_fixtures",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started: leagues/teams every "
        f"{SchedulerConfig.LEAGUE_TEAM_SYNC_INTERVAL_MINUTES}m, "
        f"fixtures every {SchedulerConfig.FIXTURE_SYNC_INTERVAL_MINUTES}m, "
        f"live fixtures every {SchedulerConfig.LIVE_FIXTURE_SYNC_INTERVAL_SECONDS}s "
        f"for {', '.join(SchedulerConfig.TRACKED_COMPETITIONS)}"
    )


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
