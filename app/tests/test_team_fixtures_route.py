"""A team's own fixtures - GET /teams/{team_id}/fixtures.

Fixtures were only queryable per-league. A team page - the single most
common thing to build against a football API - had no direct route and
had to fetch every fixture in the league and filter client-side.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.router import api_router
from app.db.database import get_session
from app.db.models import Fixture, League, Team
from app.utils.datetime_utils import utcnow

pytestmark = pytest.mark.asyncio

LEAGUE_ID = 30_000_000
OTHER_LEAGUE_ID = 30_000_100
TEAM_ID = 30_000_001
OTHER_TEAM_ID = 30_000_002
THIRD_TEAM_ID = 30_000_003


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
async def league(test_session):
    row = League(
        id=LEAGUE_ID,
        source="football_data_org",
        external_ref="PL",
        name="PL",
        current_season_year=2026,
    )
    test_session.add(row)
    await test_session.commit()
    return row


@pytest.fixture
async def teams(test_session, league):
    for team_id, name in (
        (TEAM_ID, "Home FC"),
        (OTHER_TEAM_ID, "Away FC"),
        (THIRD_TEAM_ID, "Third FC"),
    ):
        test_session.add(
            Team(
                id=team_id,
                source="football_data_org",
                league_id=LEAGUE_ID,
                season_year=2026,
                name=name,
            )
        )
    await test_session.commit()


def _fixture(fid, season_year, home_id, away_id, status="scheduled", **kw):
    return Fixture(
        id=fid,
        league_id=LEAGUE_ID,
        season_year=season_year,
        source="football_data_org",
        home_team_id=home_id,
        away_team_id=away_id,
        kickoff_at=utcnow(),
        status=status,
        **kw,
    )


class TestTeamFixtures:
    async def test_returns_fixtures_where_team_is_home_or_away(
        self, client, test_session, teams
    ):
        test_session.add(_fixture(1, 2026, TEAM_ID, OTHER_TEAM_ID))
        test_session.add(_fixture(2, 2026, OTHER_TEAM_ID, TEAM_ID))
        # Doesn't involve TEAM_ID at all - must not show up.
        test_session.add(_fixture(3, 2026, OTHER_TEAM_ID, THIRD_TEAM_ID))
        await test_session.commit()

        body = (await client.get(f"/api/v1/teams/{TEAM_ID}/fixtures")).json()
        assert body["total"] == 2
        assert {f["id"] for f in body["items"]} == {1, 2}

    async def test_defaults_to_the_teams_league_current_season(
        self, client, test_session, teams
    ):
        test_session.add(_fixture(1, 2026, TEAM_ID, OTHER_TEAM_ID))
        test_session.add(_fixture(2, 2025, TEAM_ID, OTHER_TEAM_ID))
        await test_session.commit()

        body = (await client.get(f"/api/v1/teams/{TEAM_ID}/fixtures")).json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == 1

    async def test_season_param_overrides_the_default(
        self, client, test_session, teams
    ):
        test_session.add(_fixture(1, 2026, TEAM_ID, OTHER_TEAM_ID))
        test_session.add(_fixture(2, 2025, TEAM_ID, OTHER_TEAM_ID))
        await test_session.commit()

        body = (
            await client.get(f"/api/v1/teams/{TEAM_ID}/fixtures", params={"season": 2025})
        ).json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == 2

    async def test_status_filter(self, client, test_session, teams):
        test_session.add(_fixture(1, 2026, TEAM_ID, OTHER_TEAM_ID, status="finished"))
        test_session.add(_fixture(2, 2026, TEAM_ID, OTHER_TEAM_ID, status="scheduled"))
        await test_session.commit()

        body = (
            await client.get(
                f"/api/v1/teams/{TEAM_ID}/fixtures", params={"status": "finished"}
            )
        ).json()
        assert body["total"] == 1
        assert body["items"][0]["status"] == "finished"

    async def test_unknown_team_is_404(self, client):
        r = await client.get("/api/v1/teams/99999999/fixtures")
        assert r.status_code == 404

    async def test_no_current_season_returns_empty_not_error(
        self, client, test_session
    ):
        league = League(
            id=OTHER_LEAGUE_ID, source="football_data_org", external_ref="XX", name="XX"
        )
        team = Team(
            id=THIRD_TEAM_ID + 1,
            source="football_data_org",
            league_id=OTHER_LEAGUE_ID,
            season_year=2026,
            name="No Season FC",
        )
        test_session.add(league)
        test_session.add(team)
        await test_session.commit()

        body = (
            await client.get(f"/api/v1/teams/{THIRD_TEAM_ID + 1}/fixtures")
        ).json()
        assert body == {"items": [], "total": 0}
