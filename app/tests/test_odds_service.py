"""Capturing pre-match odds.

Odds are the one thing here that cannot be re-fetched - upstream serves
them only while a fixture is upcoming. So these lean on the cases where a
capture is missed, because those holes are permanent and nothing
downstream will heal them.
"""

from datetime import timedelta

import pytest
from sqlmodel import select

from app.connectors.api_football import DailyBudgetExceeded, NormalizedOdds
from app.db.models import EntityType, Fixture, League, Odds, Team
from app.services.id_mapper import IdMapper
from app.services.odds_service import CAPTURE_WINDOW, OddsService
from app.utils.datetime_utils import utcnow

pytestmark = pytest.mark.asyncio

FIXTURE_ID = 10_000_600
THEIR_REF = "5551"


class FakeConnector:
    source = "api_football"

    def __init__(self, odds=None, budget_after=None):
        self._odds = odds if odds is not None else []
        self._budget_after = budget_after
        self.calls = 0

    async def fetch_odds(self, fixture_ref):
        self.calls += 1
        if self._budget_after is not None and self.calls > self._budget_after:
            raise DailyBudgetExceeded("spent")
        return self._odds


async def _fixture(session, kickoff_in=timedelta(hours=2), fixture_id=FIXTURE_ID):
    if not await session.get(League, 10_000_000):
        session.add(League(id=10_000_000, source="fd", external_ref="PL", name="PL"))
        session.add(
            Team(
                id=10_000_001,
                source="fd",
                league_id=10_000_000,
                season_year=2026,
                name="Home",
            )
        )
        session.add(
            Team(
                id=10_000_002,
                source="fd",
                league_id=10_000_000,
                season_year=2026,
                name="Away",
            )
        )
    fixture = Fixture(
        id=fixture_id,
        league_id=10_000_000,
        season_year=2026,
        source="fd",
        home_team_id=10_000_001,
        away_team_id=10_000_002,
        kickoff_at=utcnow() + kickoff_in,
        status="scheduled",
    )
    session.add(fixture)
    await session.commit()
    return fixture


def _prices(bookmaker="Bet365", home=2.1, draw=3.4, away=3.6):
    return NormalizedOdds(
        fixture_external_ref=THEIR_REF,
        bookmaker=bookmaker,
        home=home,
        draw=draw,
        away=away,
    )


async def _map(session, fixture_id=FIXTURE_ID, ref=THEIR_REF, verified=True):
    await IdMapper(session).link(
        EntityType.FIXTURE, "api_football", ref, fixture_id, verified=verified
    )
    await session.commit()


class TestCapture:
    async def test_captures_every_bookmaker(self, test_session):
        await _fixture(test_session)
        await _map(test_session)
        connector = FakeConnector([_prices("A"), _prices("B")])

        summary = await OddsService(test_session, connector).capture_upcoming()

        assert summary["captured"] == 1
        assert len((await test_session.exec(select(Odds))).all()) == 2

    async def test_recapture_updates_in_place(self, test_session):
        """Prices move. Keeping every observation would be a price-history
        feature - a different thing, and one that would quietly make this
        the largest table here."""
        await _fixture(test_session)
        await _map(test_session)

        await OddsService(
            test_session, FakeConnector([_prices(home=2.1)])
        ).capture_upcoming()
        await OddsService(
            test_session, FakeConnector([_prices(home=1.9)])
        ).capture_upcoming()

        rows = (await test_session.exec(select(Odds))).all()
        assert len(rows) == 1
        assert rows[0].home == 1.9

    async def test_captured_at_moves_with_a_recapture(self, test_session):
        await _fixture(test_session)
        await _map(test_session)
        service = OddsService(test_session, FakeConnector([_prices()]))
        await service.capture_upcoming()
        first = (await test_session.exec(select(Odds))).first().captured_at

        await OddsService(
            test_session, FakeConnector([_prices(home=1.5)])
        ).capture_upcoming()
        assert (await test_session.exec(select(Odds))).first().captured_at >= first


class TestWindow:
    async def test_a_fixture_beyond_the_window_is_not_captured_yet(self, test_session):
        await _fixture(test_session, kickoff_in=CAPTURE_WINDOW + timedelta(hours=2))
        await _map(test_session)
        connector = FakeConnector([_prices()])

        summary = await OddsService(test_session, connector).capture_upcoming()

        assert summary["fixtures_in_window"] == 0
        # No mapping lookup, no request - the budget is 100/day.
        assert connector.calls == 0

    async def test_a_kicked_off_fixture_is_not_attempted(self, test_session):
        """Odds stop existing at kickoff. Asking spends a request to learn
        nothing."""
        await _fixture(test_session, kickoff_in=timedelta(hours=-1))
        await _map(test_session)
        connector = FakeConnector([_prices()])

        await OddsService(test_session, connector).capture_upcoming()
        assert connector.calls == 0


class TestMissedCaptures:
    async def test_an_unmapped_fixture_is_reported_not_skipped_quietly(
        self, test_session
    ):
        """Its odds will never exist, and the deadline for fixing the
        mapping is kickoff."""
        await _fixture(test_session)
        connector = FakeConnector([_prices()])

        summary = await OddsService(test_session, connector).capture_upcoming()

        assert summary["unmapped"] == 1
        assert summary["captured"] == 0
        assert connector.calls == 0

    async def test_an_unverified_mapping_is_not_used(self, test_session):
        """A guessed mapping would attach one match's odds to another."""
        await _fixture(test_session)
        await _map(test_session, verified=False)
        connector = FakeConnector([_prices()])

        summary = await OddsService(test_session, connector).capture_upcoming()
        assert summary["unmapped"] == 1

    async def test_a_fixture_nobody_priced_is_distinguished_from_a_failure(
        self, test_session
    ):
        await _fixture(test_session)
        await _map(test_session)

        summary = await OddsService(test_session, FakeConnector([])).capture_upcoming()

        assert summary["no_odds_offered"] == 1
        assert summary["unmapped"] == 0

    async def test_running_out_of_budget_stops_rather_than_grinding(self, test_session):
        """Continuing would spend nothing useful and bury the real signal -
        which fixtures were never reached."""
        await _fixture(test_session, fixture_id=FIXTURE_ID)
        await _fixture(test_session, fixture_id=FIXTURE_ID + 1)
        await _map(test_session, FIXTURE_ID, "5551")
        await _map(test_session, FIXTURE_ID + 1, "5552")
        connector = FakeConnector([_prices()], budget_after=1)

        summary = await OddsService(test_session, connector).capture_upcoming()

        assert summary["captured"] == 1
        # Stopped on the second rather than attempting the rest.
        assert connector.calls == 2
