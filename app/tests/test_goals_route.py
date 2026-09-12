"""Goal events derived from shot data.

football-data.org exposes no goal events at the current tier, so these are
read out of Understat's shot feed. The two things worth protecting are the
ones that produce a plausible-looking but wrong scoreline: own goals
credited to the team that conceded them, and one event stored twice.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.router import api_router
from app.db.database import get_session
from app.db.models import Fixture, League, ShotEvent, Team, TeamMatchStat
from app.utils.datetime_utils import utcnow

pytestmark = pytest.mark.asyncio

HOME_ID = 10_000_001
AWAY_ID = 10_000_002
FIXTURE_ID = 10_000_500


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
async def fixture(test_session):
    league = League(
        id=10_000_000, source="football_data_org", external_ref="PL", name="PL"
    )
    test_session.add(league)
    for team_id, name in ((HOME_ID, "Home FC"), (AWAY_ID, "Away FC")):
        test_session.add(
            Team(
                id=team_id, source="football_data_org", league_id=league.id,
                season_year=2026, name=name,
            )
        )
    row = Fixture(
        id=FIXTURE_ID, league_id=league.id, season_year=2026,
        source="football_data_org", home_team_id=HOME_ID, away_team_id=AWAY_ID,
        kickoff_at=utcnow(), status="finished", home_score=2, away_score=0,
    )
    test_session.add(row)
    await test_session.commit()
    return row


def _shot(ref, player, minute, result, team_id, assist=None):
    return ShotEvent(
        fixture_id=FIXTURE_ID, team_id=team_id, source="understat",
        external_ref=ref, player_name=player, assist_player_name=assist,
        minute=minute, xg=0.5, location_x=0.9, location_y=0.5, result=result,
    )


class TestGoals:
    async def test_returns_goals_with_scorer_assist_and_minute(
        self, client, test_session, fixture
    ):
        test_session.add(_shot("1", "Scorer", 14, "Goal", HOME_ID, assist="Assister"))
        test_session.add(_shot("2", "Missed", 20, "Missed Shot", HOME_ID))
        await test_session.commit()

        body = (await client.get(f"/api/v1/fixtures/{FIXTURE_ID}/goals")).json()

        assert body["total"] == 1
        goal = body["items"][0]
        assert (goal["player_name"], goal["assist_player_name"], goal["minute"]) == (
            "Scorer", "Assister", 14,
        )

    async def test_own_goal_is_credited_to_the_opposing_team(
        self, client, test_session, fixture
    ):
        """Upstream records the shot against the team of the player who took
        it. Crediting that directly hands the goal to the side that
        conceded - verified against a real 4-0 where three home goals plus
        one away own goal made the four on the scoreboard."""
        test_session.add(_shot("1", "Unlucky Defender", 7, "Own Goal", AWAY_ID))
        await test_session.commit()

        body = (await client.get(f"/api/v1/fixtures/{FIXTURE_ID}/goals")).json()
        goal = body["items"][0]

        assert goal["is_own_goal"] is True
        assert goal["player_team_id"] == AWAY_ID  # who kicked it
        assert goal["team_id"] == HOME_ID  # who it counts for

    async def test_one_event_stored_twice_is_counted_once(
        self, client, test_session, fixture
    ):
        """Seen upstream: every goal in a fixture duplicated under two shot
        ids, making the derived score exactly double the real one."""
        test_session.add(_shot("692710", "Nicolas Pepe", 18, "Goal", HOME_ID))
        test_session.add(_shot("692711", "Nicolas Pepe", 18, "Goal", HOME_ID))
        await test_session.commit()

        body = (await client.get(f"/api/v1/fixtures/{FIXTURE_ID}/goals")).json()
        assert body["total"] == 1

    async def test_same_player_scoring_in_different_minutes_is_two_goals(
        self, client, test_session, fixture
    ):
        """The dedupe must not swallow a genuine brace."""
        test_session.add(_shot("1", "Striker", 18, "Goal", HOME_ID))
        test_session.add(_shot("2", "Striker", 64, "Goal", HOME_ID))
        await test_session.commit()

        assert (await client.get(f"/api/v1/fixtures/{FIXTURE_ID}/goals")).json()[
            "total"
        ] == 2

    async def test_goals_are_ordered_by_minute(self, client, test_session, fixture):
        test_session.add(_shot("1", "Late", 80, "Goal", HOME_ID))
        test_session.add(_shot("2", "Early", 10, "Goal", HOME_ID))
        await test_session.commit()

        items = (await client.get(f"/api/v1/fixtures/{FIXTURE_ID}/goals")).json()["items"]
        assert [g["minute"] for g in items] == [10, 80]


class TestEnrichedFlag:
    async def test_no_data_is_not_reported_as_a_goalless_match(
        self, client, fixture
    ):
        """Both cases return an empty list. A consumer that cannot tell them
        apart will render 0-0 for a match it simply has no data on."""
        body = (await client.get(f"/api/v1/fixtures/{FIXTURE_ID}/goals")).json()
        assert body["items"] == []
        assert body["enriched"] is False
        assert body["source"] is None

    async def test_a_genuine_goalless_match_is_marked_enriched(
        self, client, test_session, fixture
    ):
        test_session.add(_shot("1", "Missed It", 30, "Missed Shot", HOME_ID))
        await test_session.commit()

        body = (await client.get(f"/api/v1/fixtures/{FIXTURE_ID}/goals")).json()
        assert body["items"] == []
        assert body["enriched"] is True
        assert body["source"] == "understat"

    async def test_enrichment_without_shots_still_counts_as_enriched(
        self, client, test_session, fixture
    ):
        """A match with no shots recorded at all is vanishingly rare, but the
        team stats prove we did fetch it."""
        test_session.add(
            TeamMatchStat(
                fixture_id=FIXTURE_ID, team_id=HOME_ID, source="understat", xg=0.0
            )
        )
        await test_session.commit()

        body = (await client.get(f"/api/v1/fixtures/{FIXTURE_ID}/goals")).json()
        assert body["enriched"] is True


class TestMissingFixture:
    async def test_unknown_fixture_is_404(self, client):
        assert (await client.get("/api/v1/fixtures/99999999/goals")).status_code == 404
