from fastapi import APIRouter

from app.api.v1.routes import admin, fixtures, leagues, teams

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(leagues.router)
api_router.include_router(teams.router)
api_router.include_router(fixtures.router)
api_router.include_router(admin.router)
