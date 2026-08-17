from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logger import logger
from app.scheduler.start_scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} ({settings.ENVIRONMENT})")
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
