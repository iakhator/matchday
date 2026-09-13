from fastapi import APIRouter, Depends

from app.api.v1.routes import (
    admin,
    fixture_stats,
    fixtures,
    leagues,
    lookup,
    player_stats,
    standings,
    teams,
)
from app.core.versioning import add_version_header

# The version header is applied here rather than per-route, so a new
# route cannot be added without it.
api_router = APIRouter(prefix="/api/v1", dependencies=[Depends(add_version_header)])
api_router.include_router(leagues.router)
api_router.include_router(teams.router)
api_router.include_router(fixtures.router)
api_router.include_router(fixture_stats.router)
api_router.include_router(standings.router)
api_router.include_router(player_stats.router)
api_router.include_router(lookup.router)
api_router.include_router(admin.router)
