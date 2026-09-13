from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.heartbeat import get_job_health, seed_heartbeats_on_startup
from app.core.logger import logger
from app.db.database import async_session, get_session
from app.scheduler.start_scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} ({settings.ENVIRONMENT})")
    async with async_session() as session:
        await seed_heartbeats_on_startup(session)
    start_scheduler()
    yield
    stop_scheduler()
    logger.info("Shut down cleanly")


app = FastAPI(
    title="matchday-gateway",
    description=(
        "Self-hosted football data gateway. Aggregates leagues, teams, "
        "fixtures and scores from pluggable upstream connectors and "
        "serves them through a stable REST API."
    ),
    lifespan=lifespan,
)

app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.APP_NAME}


@app.get("/health/scheduler")
async def health_scheduler(session: AsyncSession = Depends(get_session)):
    """Reports unhealthy the moment any scheduled job's heartbeat has
    lapsed - see app/core/heartbeat.py for why this exists and how
    staleness is decided. Point an external uptime monitor at this
    instead of relying on someone noticing a silently dead scheduler."""
    jobs = await get_job_health(session)
    stale_jobs = [job["job_id"] for job in jobs if job["stale"]]

    body = {
        "status": "unhealthy" if stale_jobs else "healthy",
        "stale_jobs": stale_jobs,
        "jobs": jobs,
    }

    # 503, not 200-with-a-sad-body. Uptime monitors alert on the status
    # code by default - UptimeRobot, BetterStack, Pingdom, Kubernetes
    # probes all do. This endpoint previously returned 200 while saying
    # "unhealthy", so a monitor pointed at it would have stayed quiet
    # forever while the scheduler was dead: the exact failure it exists to
    # catch, defeated by the status code.
    if stale_jobs:
        return JSONResponse(status_code=503, content=body)
    return body
