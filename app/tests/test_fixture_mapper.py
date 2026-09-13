"""Matching a second provider's fixtures onto ours.

A wrong mapping does not fail loudly. It attaches one match's goals or odds
to a different match, and the first symptom is a scoreline nobody can
explain. So these lean on the refusals: ambiguity, near-misses and partial
matches must all produce *no* mapping rather than a plausible one.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.connectors.api_football import NormalizedFixtureRef
from app.db.models import EntityType, Fixture, League, Team
from app.services.fixture_mapper import FixtureMapper
from app.services.id_mapper import IdMapper

pytestmark = pytest.mark.asyncio

MATCHDAY = date(2026, 9, 13)
KICKOFF = datetime(2026, 9, 13, 14, 0, tzinfo=timezone.utc)


class FakeConnector:
    """Returns canned fixtures and counts requests, so the budget
    behaviour is observable without calling anything."""

    source = "api_football"

    def __init__(self, fixtures):
        self._fixtures = fixtures
        self.calls = 0

    async def fetch_fixtures_for_date(self, on):
        self.calls += 1
        return self._fixtures


async def _seed(session, pairs, kickoff=KICKOFF, offset=0):
    """`offset` lets a test seed a second, distinct set of rows - the
    ambiguity case needs two fixtures between the same clubs."""
    league = await session.get(League, 10_000_000)
    if not league:
        league = League(
            id=10_000_000, source="football_data_org", external_ref="PL", name="PL"
        )
        session.add(league)

    fixtures, team_id = [], 10_000_000 + offset
    for home_name, away_name in pairs:
        home = Team(
            id=team_id,
            source="football_data_org",
            league_id=league.id,
            season_year=2026,
            name=home_name,
            display_name=home_name,
        )
        away = Team(
            id=team_id + 1,
            source="football_data_org",
            league_id=league.id,
            season_year=2026,
            name=away_name,
            display_name=away_name,
        )
        session.add(home)
        session.add(away)
        fixture = Fixture(
            id=10_000_500 + offset + len(fixtures),
            league_id=league.id,
            season_year=2026,
            source="football_data_org",
            home_team_id=home.id,
            away_team_id=away.id,
            kickoff_at=kickoff,
            status="scheduled",
        )
        session.add(fixture)
        fixtures.append(fixture)
        team_id += 2

    await session.commit()
    return fixtures


def _theirs(ref, home, away, kickoff=KICKOFF, home_ref="500", away_ref="501"):
    return NormalizedFixtureRef(
        external_ref=ref,
        kickoff_at=kickoff,
        home_team_name=home,
        away_team_name=away,
        home_team_external_ref=home_ref,
        away_team_external_ref=away_ref,
        league_external_ref="39",
    )


class TestMatching:
    async def test_maps_a_fixture_both_providers_agree_on(self, test_session):
        [fixture] = await _seed(test_session, [("Arsenal FC", "Chelsea FC")])
        mapper = FixtureMapper(
            test_session, FakeConnector([_theirs("999", "Arsenal", "Chelsea")])
        )

        created = await mapper.map_date(MATCHDAY)

        assert created == {"999": fixture.id}
        assert (
            await IdMapper(test_session).resolve(
                EntityType.FIXTURE, "api_football", "999"
            )
            == fixture.id
        )

    async def test_an_exact_match_is_trusted_without_review(self, test_session):
        """Both clubs identical once normalized, kickoffs within an hour.

        To be wrong here you would need two different matches between the
        same two clubs kicking off within an hour of each other, which does
        not happen - so this is certainty, not inference. It has to work
        unattended: new fixtures arrive weekly, and requiring review for
        each would leave goals and odds permanently behind."""
        await _seed(test_session, [("Arsenal FC", "Chelsea FC")])
        mapper = FixtureMapper(
            test_session, FakeConnector([_theirs("999", "Arsenal", "Chelsea")])
        )
        await mapper.map_date(MATCHDAY)

        [row] = await IdMapper(test_session).aliases(EntityType.FIXTURE, 10_000_500)
        assert row.verified is True

    async def test_a_fuzzy_match_stays_unverified(self, test_session):
        """ "Brighton" only matches "Brighton & Hove Albion FC" by prefix.
        Good enough to propose, not to act on - #4's rule."""
        await _seed(test_session, [("Brighton & Hove Albion FC", "Chelsea FC")])
        mapper = FixtureMapper(
            test_session, FakeConnector([_theirs("999", "Brighton", "Chelsea")])
        )
        await mapper.map_date(MATCHDAY)

        [row] = await IdMapper(test_session).aliases(EntityType.FIXTURE, 10_000_500)
        assert row.verified is False

    async def test_clubs_are_mapped_alongside_a_certain_fixture(self, test_session):
        """Goal events are attributed by team ref, so a fixture mapping
        alone cannot say which side scored. The ids are in the same
        response, so this costs no extra request."""
        await _seed(test_session, [("Arsenal FC", "Chelsea FC")])
        mapper = FixtureMapper(
            test_session,
            FakeConnector(
                [_theirs("999", "Arsenal", "Chelsea", home_ref="42", away_ref="49")]
            ),
        )
        await mapper.map_date(MATCHDAY)

        ids = IdMapper(test_session)
        assert await ids.resolve(EntityType.TEAM, "api_football", "42") == 10_000_000
        assert await ids.resolve(EntityType.TEAM, "api_football", "49") == 10_000_001

    async def test_clubs_are_not_mapped_from_a_fuzzy_fixture(self, test_session):
        """Deriving a club mapping from an uncertain fixture would spread
        one guess into two."""
        await _seed(test_session, [("Brighton & Hove Albion FC", "Chelsea FC")])
        mapper = FixtureMapper(
            test_session,
            FakeConnector(
                [_theirs("999", "Brighton", "Chelsea", home_ref="42", away_ref="49")]
            ),
        )
        await mapper.map_date(MATCHDAY)

        assert (
            await IdMapper(test_session).resolve(EntityType.TEAM, "api_football", "42")
            is None
        )

    async def test_matches_through_the_display_name(self, test_session):
        """Providers publish different forms of a club's name. Brighton is
        the case that broke a naive matcher before."""
        await _seed(test_session, [("Brighton & Hove Albion FC", "Chelsea FC")])
        mapper = FixtureMapper(
            test_session, FakeConnector([_theirs("999", "Brighton", "Chelsea")])
        )

        assert await mapper.map_date(MATCHDAY) != {}

    async def test_both_teams_must_match(self, test_session):
        """Matching on one end would map to the wrong opponent whenever a
        club plays twice in a window."""
        await _seed(test_session, [("Arsenal FC", "Chelsea FC")])
        mapper = FixtureMapper(
            test_session, FakeConnector([_theirs("999", "Arsenal", "Everton")])
        )

        assert await mapper.map_date(MATCHDAY) == {}

    async def test_home_and_away_are_not_interchangeable(self, test_session):
        """A reversed fixture is a different match."""
        await _seed(test_session, [("Arsenal FC", "Chelsea FC")])
        mapper = FixtureMapper(
            test_session, FakeConnector([_theirs("999", "Chelsea", "Arsenal")])
        )

        assert await mapper.map_date(MATCHDAY) == {}

    async def test_a_kickoff_far_away_is_a_different_fixture(self, test_session):
        """Same clubs, two days apart - a return leg, not a timezone
        disagreement."""
        await _seed(test_session, [("Arsenal FC", "Chelsea FC")])
        mapper = FixtureMapper(
            test_session,
            FakeConnector(
                [_theirs("999", "Arsenal", "Chelsea", KICKOFF + timedelta(days=2))]
            ),
        )

        assert await mapper.map_date(MATCHDAY) == {}

    async def test_a_timezone_sized_difference_still_matches(self, test_session):
        """Providers disagree by an offset; they do not disagree by half a
        day."""
        await _seed(test_session, [("Arsenal FC", "Chelsea FC")])
        mapper = FixtureMapper(
            test_session,
            FakeConnector(
                [_theirs("999", "Arsenal", "Chelsea", KICKOFF + timedelta(hours=1))]
            ),
        )

        assert await mapper.map_date(MATCHDAY) != {}


class TestRefusals:
    async def test_ambiguity_produces_no_mapping(self, test_session):
        """Two of our fixtures equally consistent with theirs. A missing
        mapping costs one fixture's odds; a wrong one corrupts a
        scoreline."""
        await _seed(test_session, [("Arsenal FC", "Chelsea FC")])
        await _seed(test_session, [("Arsenal FC", "Chelsea FC")], offset=100)
        mapper = FixtureMapper(
            test_session, FakeConnector([_theirs("999", "Arsenal", "Chelsea")])
        )

        assert await mapper.map_date(MATCHDAY) == {}

    async def test_a_fixture_we_do_not_hold_is_skipped(self, test_session):
        """They cover 335 leagues; we cover a handful. The overwhelming
        majority of what comes back is irrelevant and must be ignored
        silently, not treated as an error."""
        await _seed(test_session, [("Arsenal FC", "Chelsea FC")])
        mapper = FixtureMapper(
            test_session,
            FakeConnector(
                [
                    _theirs("999", "Arsenal", "Chelsea"),
                    _theirs("1000", "Santos", "Cruzeiro"),
                ]
            ),
        )

        assert list(await mapper.map_date(MATCHDAY)) == ["999"]

    async def test_no_upstream_call_when_we_hold_nothing_that_day(self, test_session):
        """The budget is 100 requests a day. Asking about a date we have no
        fixtures for spends one for nothing."""
        connector = FakeConnector([_theirs("999", "Arsenal", "Chelsea")])
        mapper = FixtureMapper(test_session, connector)

        assert await mapper.map_date(MATCHDAY) == {}
        assert connector.calls == 0

    async def test_remapping_is_idempotent(self, test_session):
        await _seed(test_session, [("Arsenal FC", "Chelsea FC")])
        connector = FakeConnector([_theirs("999", "Arsenal", "Chelsea")])
        mapper = FixtureMapper(test_session, connector)

        first = await mapper.map_date(MATCHDAY)
        second = await mapper.map_date(MATCHDAY)

        assert first != {}
        # Already mapped, so nothing new - and no duplicate alias.
        assert second == {}
        assert (
            len(await IdMapper(test_session).aliases(EntityType.FIXTURE, 10_000_500)) == 1
        )
