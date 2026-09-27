"""League discovery - country filter and available seasons.

GET /leagues had no filters at all, so a consumer had to already know a
league's id to do anything with it, and there was no way to discover what
seasons a league has data for without guessing years against /fixtures.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.router import api_router
from app.db.database import get_session
from app.db.models import Fixture, League, Standing, Team

pytestmark = pytest.mark.asyncio

PL_ID = 50_000_000
BL1_ID = 50_000_001
TEAM_A = 50_000_100
TEAM_B = 50_000_101


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
async def leagues(test_session):
    test_session.add(
        League(
            id=PL_ID, source="football_data_org", external_ref="PL",
            name="Premier League", country="England",
        )
    )
    test_session.add(
        League(
            id=BL1_ID, source="football_data_org", external_ref="BL1",
            name="Bundesliga", country="Germany",
        )
    )
    await test_session.commit()


class TestCountryFilter:
    async def test_filter_narrows_results(self, client, leagues):
        body = (await client.get("/api/v1/leagues", params={"country": "England"})).json()
        assert [league["name"] for league in body] == ["Premier League"]

    async def test_filter_is_case_insensitive(self, client, leagues):
        body = (await client.get("/api/v1/leagues", params={"country": "england"})).json()
        assert [league["name"] for league in body] == ["Premier League"]

    async def test_unknown_country_returns_empty_list_not_404(self, client, leagues):
        r = await client.get("/api/v1/leagues", params={"country": "Narnia"})
        assert r.status_code == 200
        assert r.json() == []

    async def test_no_filter_returns_everything(self, client, leagues):
        body = (await client.get("/api/v1/leagues")).json()
        assert len(body) == 2


class TestSeasons:
    async def test_returns_years_with_fixtures_or_standings_most_recent_first(
        self, client, test_session, leagues
    ):
        test_session.add(
            Team(id=TEAM_A, source="football_data_org", league_id=PL_ID,
                 season_year=2026, name="A")
        )
        test_session.add(
            Team(id=TEAM_B, source="football_data_org", league_id=PL_ID,
                 season_year=2026, name="B")
        )
        await test_session.commit()

        from app.utils.datetime_utils import utcnow

        test_session.add(
            Fixture(league_id=PL_ID, season_year=2026, source="football_data_org",
                    home_team_id=TEAM_A, away_team_id=TEAM_B, kickoff_at=utcnow(),
                    status="scheduled")
        )
        # 2024 only has a standings row (say, an older backfilled season) -
        # must still show up.
        test_session.add(
            Standing(league_id=PL_ID, season_year=2024, team_id=TEAM_A, rank=1,
                     played=0, won=0, drawn=0, lost=0, goals_for=0,
                     goals_against=0, points=0)
        )
        await test_session.commit()

        body = (await client.get(f"/api/v1/leagues/{PL_ID}/seasons")).json()
        assert body == [2026, 2024]

    async def test_league_with_no_data_returns_empty_list(self, client, leagues):
        body = (await client.get(f"/api/v1/leagues/{BL1_ID}/seasons")).json()
        assert body == []

    async def test_unknown_league_is_404(self, client):
        r = await client.get("/api/v1/leagues/99999999/seasons")
        assert r.status_code == 404
