from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.heartbeat import get_job_health, seed_heartbeats_on_startup
from app.core.logger import logger
from app.core.versioning import API_VERSION
from app.db.database import async_session, get_session
from app.scheduler.start_scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} ({settings.ENVIRONMENT})")

    if settings.ENABLE_SOCCERDATA:
        # Said out loud at startup, not only in the README. Someone
        # inheriting this deployment - or enabling the flag for the xG data
        # without reading why it is off by default - should not have to go
        # looking to find out what it turned on.
        logger.warning(
            "ENABLE_SOCCERDATA is on. The Understat and Sofascore connectors "
            "reach their sources through TLS fingerprint spoofing "
            "(soccerdata/tls_requests), which is deliberate evasion of bot "
            "detection rather than an API call with a key. See the README "
            "section 'Optional connectors, and the tradeoff they carry'."
        )

    async with async_session() as session:
        await seed_heartbeats_on_startup(session)
    start_scheduler()
    yield
    stop_scheduler()
    logger.info("Shut down cleanly")


# This metadata is the customer-facing documentation: /docs and
# /openapi.json are generated from it, so it is written for someone
# deciding whether to build against this API, not for a maintainer.
app = FastAPI(
    title="Matchday API",
    version=API_VERSION,
    description=(
        "Football data - competitions, teams, fixtures, live scores, "
        "standings and player statistics - served through one stable REST "
        "API.\n\n"
        "Identifiers belong to this API, not to whichever upstream source "
        "the data came from, so sources can change without your "
        "integration changing. Use `/api/v1/lookup` to translate "
        "identifiers you already hold from another provider.\n\n"
        "Authenticate with an `X-Gateway-Key` header. Rate limits are per "
        "key; exceeding one returns `429` with `Retry-After`.\n\n"
        "**Stability:** within `/api/v1`, changes are additive only. "
        "Breaking changes ship as a new version path alongside this one, "
        "and anything being retired carries `Deprecation` and `Sunset` "
        "headers first."
    ),
    lifespan=lifespan,
)

# Off (empty origin list) unless GATEWAY_CORS_ORIGINS is set. Only the
# /api/v1/account/* routes need this at all - every other route is called
# server-to-server, never from a browser - but CORS is applied per-app in
# FastAPI, not per-router, so it is scoped here by origin instead.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.gateway_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
