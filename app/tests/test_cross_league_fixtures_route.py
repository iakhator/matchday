"""Cross-league fixture discovery - GET /fixtures.

Every fixture query required a league_id. There was no way to ask "what's
on today" or "what's live right now" across every tracked competition
without one request per league.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.router import api_router
from app.db.database import get_session
from app.db.models import Fixture, League, Team
from app.utils.datetime_utils import utcnow

pytestmark = pytest.mark.asyncio

LEAGUE_A = 40_000_000
LEAGUE_B = 40_000_100
TEAM_A1 = 40_000_001
TEAM_A2 = 40_000_002
TEAM_B1 = 40_000_101
TEAM_B2 = 40_000_102


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
async def two_leagues(test_session):
    test_session.add(
        League(id=LEAGUE_A, source="football_data_org", external_ref="PL", name="PL")
    )
    test_session.add(
        League(id=LEAGUE_B, source="football_data_org", external_ref="BL1", name="BL1")
    )
    for team_id, league_id, name in (
        (TEAM_A1, LEAGUE_A, "A Home"),
        (TEAM_A2, LEAGUE_A, "A Away"),
        (TEAM_B1, LEAGUE_B, "B Home"),
        (TEAM_B2, LEAGUE_B, "B Away"),
    ):
        test_session.add(
            Team(
                id=team_id, source="football_data_org", league_id=league_id,
                season_year=2026, name=name,
            )
        )
    await test_session.commit()


def _fixture(fid, league_id, home_id, away_id, kickoff, status="scheduled"):
    return Fixture(
        id=fid, league_id=league_id, season_year=2026, source="football_data_org",
        home_team_id=home_id, away_team_id=away_id, kickoff_at=kickoff, status=status,
    )


class TestValidation:
    async def test_requires_a_date_range_or_status_live(self, client, two_leagues):
        r = await client.get("/api/v1/fixtures")
        assert r.status_code == 400

    async def test_one_sided_date_range_is_rejected(self, client, two_leagues):
        r = await client.get("/api/v1/fixtures", params={"date_from": "2026-09-01"})
        assert r.status_code == 400

    async def test_date_to_before_date_from_is_rejected(self, client, two_leagues):
        r = await client.get(
            "/api/v1/fixtures",
            params={"date_from": "2026-09-10", "date_to": "2026-09-01"},
        )
        assert r.status_code == 400

    async def test_range_over_the_cap_is_rejected(self, client, two_leagues):
        r = await client.get(
            "/api/v1/fixtures",
            params={"date_from": "2026-01-01", "date_to": "2026-12-31"},
        )
        assert r.status_code == 400

    async def test_status_live_needs_no_date_range(self, client, two_leagues):
        r = await client.get("/api/v1/fixtures", params={"status": "live"})
        assert r.status_code == 200


class TestDateRange:
    async def test_spans_multiple_leagues(self, client, test_session, two_leagues):
        from datetime import datetime, timezone

        in_range = datetime(2026, 9, 15, 15, 0, tzinfo=timezone.utc)
        out_of_range = datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)

        test_session.add(_fixture(1, LEAGUE_A, TEAM_A1, TEAM_A2, in_range))
        test_session.add(_fixture(2, LEAGUE_B, TEAM_B1, TEAM_B2, in_range))
        test_session.add(_fixture(3, LEAGUE_A, TEAM_A1, TEAM_A2, out_of_range))
        await test_session.commit()

        body = (
            await client.get(
                "/api/v1/fixtures",
                params={"date_from": "2026-09-01", "date_to": "2026-09-30"},
            )
        ).json()

        assert body["total"] == 2
        assert {f["id"] for f in body["items"]} == {1, 2}
        assert {f["league_id"] for f in body["items"]} == {LEAGUE_A, LEAGUE_B}

    async def test_date_bounds_are_inclusive(self, client, test_session, two_leagues):
        from datetime import datetime, timezone

        start_of_day = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
        end_of_day = datetime(2026, 9, 30, 23, 59, tzinfo=timezone.utc)

        test_session.add(_fixture(1, LEAGUE_A, TEAM_A1, TEAM_A2, start_of_day))
        test_session.add(_fixture(2, LEAGUE_A, TEAM_A1, TEAM_A2, end_of_day))
        await test_session.commit()

        body = (
            await client.get(
                "/api/v1/fixtures",
                params={"date_from": "2026-09-01", "date_to": "2026-09-30"},
            )
        ).json()
        assert body["total"] == 2


class TestLiveFilter:
    async def test_status_live_matches_across_leagues(
        self, client, test_session, two_leagues
    ):
        now = utcnow()
        test_session.add(_fixture(1, LEAGUE_A, TEAM_A1, TEAM_A2, now, status="live"))
        test_session.add(_fixture(2, LEAGUE_B, TEAM_B1, TEAM_B2, now, status="live"))
        test_session.add(
            _fixture(3, LEAGUE_A, TEAM_A1, TEAM_A2, now, status="scheduled")
        )
        await test_session.commit()

        body = (
            await client.get("/api/v1/fixtures", params={"status": "live"})
        ).json()
        assert body["total"] == 2
        assert {f["id"] for f in body["items"]} == {1, 2}

    async def test_status_live_can_be_combined_with_a_date_range(
        self, client, test_session, two_leagues
    ):
        now = utcnow()
        test_session.add(_fixture(1, LEAGUE_A, TEAM_A1, TEAM_A2, now, status="live"))
        await test_session.commit()

        body = (
            await client.get(
                "/api/v1/fixtures",
                params={
                    "status": "live",
                    "date_from": now.date().isoformat(),
                    "date_to": now.date().isoformat(),
                },
            )
        ).json()
        assert body["total"] == 1
