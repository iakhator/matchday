from fastapi import APIRouter

from app.api.v1.routes import (
    admin,
    fixture_stats,
    fixtures,
    leagues,
    player_stats,
    standings,
    teams,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(leagues.router)
api_router.include_router(teams.router)
api_router.include_router(fixtures.router)
api_router.include_router(fixture_stats.router)
api_router.include_router(standings.router)
api_router.include_router(player_stats.router)
api_router.include_router(admin.router)
