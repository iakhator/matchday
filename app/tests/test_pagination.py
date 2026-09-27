"""Pagination contract - limit/offset on fixtures, standings and
player-stats list endpoints, with `total` reflecting every matching row,
not just the ones on the current page.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.router import api_router
from app.db.database import get_session
from app.db.models import Fixture, League, PlayerStat, Standing, Team
from app.utils.datetime_utils import utcnow

pytestmark = pytest.mark.asyncio

LEAGUE_ID = 60_000_000
TEAM_IDS = [60_000_001, 60_000_002, 60_000_003, 60_000_004, 60_000_005]


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
async def league_and_teams(test_session):
    test_session.add(
        League(
            id=LEAGUE_ID, source="football_data_org", external_ref="PL",
            name="PL", current_season_year=2026,
        )
    )
    for team_id in TEAM_IDS:
        test_session.add(
            Team(id=team_id, source="football_data_org", league_id=LEAGUE_ID,
                 season_year=2026, name=f"Team {team_id}")
        )
    await test_session.commit()


class TestFixturesPagination:
    async def test_limit_caps_page_size(self, client, test_session, league_and_teams):
        for i in range(5):
            test_session.add(
                Fixture(
                    id=i, league_id=LEAGUE_ID, season_year=2026,
                    source="football_data_org", home_team_id=TEAM_IDS[0],
                    away_team_id=TEAM_IDS[1], kickoff_at=utcnow(), status="scheduled",
                )
            )
        await test_session.commit()

        body = (
            await client.get(
                f"/api/v1/leagues/{LEAGUE_ID}/fixtures", params={"limit": 2}
            )
        ).json()
        assert len(body["items"]) == 2
        assert body["total"] == 5

    async def test_offset_moves_the_window(self, client, test_session, league_and_teams):
        from datetime import timedelta

        base = utcnow()
        for i in range(5):
            test_session.add(
                Fixture(
                    id=i, league_id=LEAGUE_ID, season_year=2026,
                    source="football_data_org", home_team_id=TEAM_IDS[0],
                    away_team_id=TEAM_IDS[1], kickoff_at=base + timedelta(hours=i),
                    status="scheduled",
                )
            )
        await test_session.commit()

        page1 = (
            await client.get(
                f"/api/v1/leagues/{LEAGUE_ID}/fixtures",
                params={"limit": 2, "offset": 0},
            )
        ).json()
        page2 = (
            await client.get(
                f"/api/v1/leagues/{LEAGUE_ID}/fixtures",
                params={"limit": 2, "offset": 2},
            )
        ).json()

        assert [f["id"] for f in page1["items"]] == [0, 1]
        assert [f["id"] for f in page2["items"]] == [2, 3]
        assert page1["total"] == page2["total"] == 5

    async def test_limit_is_capped_at_100(self, client, league_and_teams):
        r = await client.get(
            f"/api/v1/leagues/{LEAGUE_ID}/fixtures", params={"limit": 500}
        )
        assert r.status_code == 422

    async def test_cross_league_fixtures_are_paginated_too(
        self, client, test_session, league_and_teams
    ):
        for i in range(5):
            test_session.add(
                Fixture(
                    id=i, league_id=LEAGUE_ID, season_year=2026,
                    source="football_data_org", home_team_id=TEAM_IDS[0],
                    away_team_id=TEAM_IDS[1], kickoff_at=utcnow(), status="live",
                )
            )
        await test_session.commit()

        body = (
            await client.get(
                "/api/v1/fixtures", params={"status": "live", "limit": 2}
            )
        ).json()
        assert len(body["items"]) == 2
        assert body["total"] == 5


class TestStandingsPagination:
    async def test_limit_and_total(self, client, test_session, league_and_teams):
        for rank, team_id in enumerate(TEAM_IDS, start=1):
            test_session.add(
                Standing(
                    league_id=LEAGUE_ID, season_year=2026, team_id=team_id, rank=rank,
                    points=0, played=0, won=0, drawn=0, lost=0, goals_for=0,
                    goals_against=0,
                )
            )
        await test_session.commit()

        body = (
            await client.get(
                f"/api/v1/leagues/{LEAGUE_ID}/standings", params={"limit": 2}
            )
        ).json()
        assert len(body["items"]) == 2
        assert body["total"] == 5
        assert [row["rank"] for row in body["items"]] == [1, 2]


class TestPlayerStatsPagination:
    async def test_limit_offset_and_total(self, client, test_session, league_and_teams):
        for i, team_id in enumerate(TEAM_IDS):
            test_session.add(
                PlayerStat(
                    team_id=team_id, season_year=2026, source="football_data_org",
                    external_ref=str(i), name=f"Player {i}", goals=5 - i,
                    assists=0, appearances=1,
                )
            )
        await test_session.commit()

        page1 = (
            await client.get(
                f"/api/v1/leagues/{LEAGUE_ID}/players", params={"limit": 2, "offset": 0}
            )
        ).json()
        page2 = (
            await client.get(
                f"/api/v1/leagues/{LEAGUE_ID}/players", params={"limit": 2, "offset": 2}
            )
        ).json()

        assert page1["total"] == page2["total"] == 5
        assert [p["name"] for p in page1["items"]] == ["Player 0", "Player 1"]
        assert [p["name"] for p in page2["items"]] == ["Player 2", "Player 3"]
