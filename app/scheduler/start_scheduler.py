from datetime import timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.logger import logger
from app.core.scheduler_config import SchedulerConfig
from app.scheduler.jobs import (
    capture_odds_job,
    map_api_football_fixtures_job,
    sync_fixtures_job,
    sync_leagues_and_teams_job,
    sync_live_fixtures_job,
    sync_standings_and_players_job,
)
from app.utils.datetime_utils import utcnow

# Defaults matter here: AsyncIOScheduler's built-in default
# misfire_grace_time is ~1 second. Every job runs on the same event loop
# as the web server, so anything that keeps the loop briefly busy around a
# job's fire time (a slow request, a connector's retry/backoff sleep, a
# neighboring job still finishing up) pushes it past that ~1s window -
# and the default behavior is to silently skip the run rather than run it
# late. Once a job misses one slot it's often still busy for the next,
# so it can stay stuck skipping for hours. misfire_grace_time=None means
# "run it whenever discovered, no matter how late"; coalesce=True means a
# job that missed several slots in a row still only runs once (catch up,
# don't backlog-replay).
scheduler = AsyncIOScheduler(
    job_defaults={"coalesce": True, "misfire_grace_time": None}
)


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
    scheduler.add_job(
        sync_standings_and_players_job,
        trigger=IntervalTrigger(
            minutes=SchedulerConfig.STANDINGS_AND_PLAYERS_SYNC_INTERVAL_MINUTES
        ),
        id="sync_standings_and_players",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started: leagues/teams every "
        f"{SchedulerConfig.LEAGUE_TEAM_SYNC_INTERVAL_MINUTES}m, "
        f"fixtures every {SchedulerConfig.FIXTURE_SYNC_INTERVAL_MINUTES}m, "
        f"live fixtures every {SchedulerConfig.LIVE_FIXTURE_SYNC_INTERVAL_SECONDS}s, "
        "standings/players every "
        f"{SchedulerConfig.STANDINGS_AND_PLAYERS_SYNC_INTERVAL_MINUTES}m "
        f"for {', '.join(SchedulerConfig.TRACKED_COMPETITIONS)}"
    )


    # start_date delays the first run. Without it an IntervalTrigger fires
    # the instant the scheduler starts, which is before the container's
    # DNS is reliably up - both of these failed on startup with "No address
    # associated with hostname" and then sat idle until their next
    # interval, a full day away for the mapping job.
    first_run = utcnow() + timedelta(seconds=SchedulerConfig.JOB_STARTUP_DELAY_SECONDS)

    scheduler.add_job(
        map_api_football_fixtures_job,
        trigger=IntervalTrigger(
            minutes=SchedulerConfig.FIXTURE_MAPPING_INTERVAL_MINUTES,
            start_date=first_run,
        ),
        id="map_api_football_fixtures",
        replace_existing=True,
    )
    scheduler.add_job(
        capture_odds_job,
        trigger=IntervalTrigger(
            minutes=SchedulerConfig.ODDS_CAPTURE_INTERVAL_MINUTES,
            start_date=first_run,
        ),
        id="capture_odds",
        replace_existing=True,
    )


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
