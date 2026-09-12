"""
Scheduler job heartbeats.

Predify's own scheduler went silently dead for hours with nothing to
notice on its own - the same failure mode is possible here. Each
scheduled job stamps a `SchedulerHeartbeat` row on its success path; a job
that's actually running keeps that stamp fresh. `/health` (see
app/main.py) compares each row's age against that job's own sync interval
plus a grace period and reports unhealthy the moment one goes stale, so an
external uptime monitor can catch it instead of someone noticing by
accident.
"""

from typing import Dict, List

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logger import logger
from app.core.scheduler_config import SchedulerConfig
from app.db.models.scheduler_heartbeat import SchedulerHeartbeat
from app.utils.datetime_utils import ensure_utc, utcnow

# Grace period per job, in seconds - generous enough to absorb one
# slow/delayed run without a false alarm, tight enough to still catch a
# genuinely dead scheduler quickly. Derived from each job's own interval
# (2x the interval, so a single missed cycle never trips it) with a small
# floor for the fastest job so normal scheduling jitter doesn't either.
JOB_GRACE_SECONDS: Dict[str, int] = {
    "sync_leagues_and_teams": SchedulerConfig.LEAGUE_TEAM_SYNC_INTERVAL_MINUTES * 60 * 2,
    "sync_fixtures": SchedulerConfig.FIXTURE_SYNC_INTERVAL_MINUTES * 60 * 2,
    "sync_standings_and_players": (
        SchedulerConfig.STANDINGS_AND_PLAYERS_SYNC_INTERVAL_MINUTES * 60 * 2
    ),
    "sync_live_fixtures": max(
        SchedulerConfig.LIVE_FIXTURE_SYNC_INTERVAL_SECONDS * 2, 300
    ),
}


async def record_heartbeat(session: AsyncSession, job_id: str) -> None:
    """Call on a scheduled job's success path only - never from an except
    branch. A job that's erroring every run should still go stale and
    alert, not look healthy because it keeps trying."""
    if job_id not in JOB_GRACE_SECONDS:
        logger.warning(f"No grace period configured for heartbeat job '{job_id}'")
        return
    try:
        existing = await session.get(SchedulerHeartbeat, job_id)
        if existing:
            existing.last_run_at = utcnow()
            session.add(existing)
        else:
            session.add(SchedulerHeartbeat(job_id=job_id, last_run_at=utcnow()))
        await session.commit()
    except Exception:
        logger.exception(f"Failed to record heartbeat for '{job_id}'")


async def seed_heartbeats_on_startup(session: AsyncSession) -> None:
    """Called once when the app starts. Without this, every job looks
    'stale' for up to its own interval after a fresh deploy simply because
    it hasn't had a chance to run yet - a guaranteed false alarm. Seeding
    treats startup as provisional good faith for one cycle; a real job run
    refreshes its own row sooner anyway, so this only masks a true failure
    for at most one extra cycle, not indefinitely. Only seeds rows that
    don't already exist, so a restart never resets a genuinely stale job
    back to healthy.
    """
    for job_id in JOB_GRACE_SECONDS:
        try:
            existing = await session.get(SchedulerHeartbeat, job_id)
            if not existing:
                session.add(SchedulerHeartbeat(job_id=job_id, last_run_at=utcnow()))
                await session.commit()
        except Exception:
            logger.exception(f"Failed to seed heartbeat for '{job_id}'")


async def get_stale_jobs(session: AsyncSession) -> List[str]:
    """Job ids whose heartbeat has expired or never fired - what's
    actually wrong, if anything."""
    rows = (await session.exec(select(SchedulerHeartbeat))).all()
    last_run_by_job = {row.job_id: row.last_run_at for row in rows}

    now = utcnow()
    stale = []
    for job_id, grace_seconds in JOB_GRACE_SECONDS.items():
        last_run_at = last_run_by_job.get(job_id)
        if last_run_at is None:
            stale.append(job_id)
            continue
        age_seconds = (now - ensure_utc(last_run_at)).total_seconds()
        if age_seconds > grace_seconds:
            stale.append(job_id)
    return stale
