"""
Entrypoint for the standalone `scheduler` process (see
docker-entrypoint.sh). `app.main` (the `serve` process) never runs
`start_scheduler()` itself - this is the only process that does, same as
`migrate` is the only place `alembic upgrade` runs. No API routes here,
just a liveness endpoint for the container healthcheck.

`GET /health/scheduler` deliberately does NOT live here. It reads the
`SchedulerHeartbeat` table (see app/core/heartbeat.py), not in-process
scheduler state, so the API process can keep serving it unchanged - as a
read-only view - regardless of which process is actually running the
jobs. Moving it here would mean consumers change hosts for no reason.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.heartbeat import seed_heartbeats_on_startup
from app.core.logger import logger
from app.db.database import async_session
from app.scheduler.start_scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting scheduler process")
    async with async_session() as session:
        await seed_heartbeats_on_startup(session)
    start_scheduler()
    yield
    stop_scheduler()
    logger.info("Scheduler process shut down cleanly")


app = FastAPI(title="Matchday Scheduler", lifespan=lifespan)


@app.get("/health")
async def health():
    """Liveness only - is this process up? Job-level health is
    `GET /health/scheduler` on the API process; see the module docstring
    for why that stays there."""
    return {"status": "ok", "service": "matchday-scheduler"}
