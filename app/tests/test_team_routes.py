"""Team detail - direct lookup by the id this gateway already hands out.

Teams were only reachable through GET /leagues/{league_id}/teams. A
consumer holding a team id from a fixture, a standing or a lookup response
had no way to fetch that team directly without already knowing its league.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.router import api_router
from app.db.database import get_session
from app.db.models import League, Team

pytestmark = pytest.mark.asyncio

LEAGUE_ID = 20_000_000
TEAM_ID = 20_000_001


@pytest.fixture
async def client(test_session):
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(api_router)
    app.dependency_overrides[get_session] = lambda: test_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.fixture
async def team(test_session):
    league = League(
        id=LEAGUE_ID, source="football_data_org", external_ref="PL", name="PL"
    )
    test_session.add(league)
    row = Team(
        id=TEAM_ID,
        source="football_data_org",
        league_id=LEAGUE_ID,
        season_year=2026,
        name="Home FC",
        short_name="Home",
    )
    test_session.add(row)
    await test_session.commit()
    return row


class TestGetTeam:
    async def test_known_id_returns_the_team(self, client, team):
        body = (await client.get(f"/api/v1/teams/{TEAM_ID}")).json()
        assert body["id"] == TEAM_ID
        assert body["name"] == "Home FC"
        assert body["league_id"] == LEAGUE_ID

    async def test_unknown_id_is_404(self, client):
        r = await client.get("/api/v1/teams/99999999")
        assert r.status_code == 404
