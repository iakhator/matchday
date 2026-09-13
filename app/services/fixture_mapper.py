"""Matching api-football's fixtures onto the ones this gateway already holds.

Goal events and odds are fetched per fixture, by api-football's id. We hold
fixtures under our own ids, synced from football-data.org. Nothing connects
the two - the providers share no identifiers - so they have to be matched
on what a fixture *is*: who played, and when.

This is the problem `external_ids` (#3) and the name matcher (#4) were built
for, now with a second provider actually in play rather than hypothetical.

Matching is deliberately strict. A wrong mapping does not fail loudly - it
quietly attaches one match's goals to a different match, and the first sign
is a scoreline that makes no sense. So:

  - both teams must match, not one
  - kickoff must agree to within a few hours, which tolerates a provider
    listing a different timezone offset but not a different fixture
  - anything ambiguous is skipped and reported, never guessed
"""

from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors.api_football import ApiFootballConnector, NormalizedFixtureRef
from app.core.logger import logger
from app.db.models import EntityType, Fixture, Team
from app.services.id_mapper import IdMapper
from app.services.name_matcher import normalize
from app.utils.datetime_utils import ensure_utc

# How far apart two kickoffs can be and still be the same match. Providers
# occasionally disagree by a timezone offset or publish a provisional time;
# they do not disagree by half a day. Wide enough to absorb the former,
# narrow enough that two fixtures between the same clubs in one day - a
# double-header in a cup competition - cannot collide.
KICKOFF_TOLERANCE = timedelta(hours=6)


class FixtureMapper:
    def __init__(self, session: AsyncSession, connector: ApiFootballConnector):
        self.session = session
        self.connector = connector
        self.ids = IdMapper(session)

    async def map_date(self, on: date) -> Dict[str, int]:
        """Map every api-football fixture on `on` to a fixture we hold.

        One upstream request covers every competition - 1,130 fixtures
        across 335 leagues on a busy Saturday. Asking per league would cost
        a request each and spend the day's budget before lunchtime.

        Returns the mappings created this run, keyed by api-football's id.
        """
        ours = await self._our_fixtures_on(on)
        if not ours:
            logger.info(f"No fixtures held for {on.isoformat()}, nothing to map")
            return {}

        theirs = await self.connector.fetch_fixtures_for_date(on)

        created: Dict[str, int] = {}
        ambiguous = 0
        for candidate in theirs:
            existing = await self.ids.resolve(
                EntityType.FIXTURE, self.connector.source, candidate.external_ref
            )
            if existing is not None:
                continue

            matches = []
            for held in ours:
                if await self._same_fixture(held, candidate):
                    matches.append(held)

            if len(matches) > 1:
                # Two of our fixtures equally consistent with theirs. Rather
                # than pick, leave it unmapped - a missing mapping costs one
                # fixture's odds; a wrong one corrupts a scoreline.
                ambiguous += 1
                continue
            if not matches:
                continue

            fixture = matches[0]
            await self.ids.link(
                EntityType.FIXTURE,
                self.connector.source,
                candidate.external_ref,
                fixture.id,
                # Matched on names and kickoff, not on an identifier either
                # provider published. That is an inference, and #4's rule is
                # that an inference is a suggestion until a human confirms
                # it.
                verified=False,
            )
            created[candidate.external_ref] = fixture.id

        await self.session.commit()
        logger.info(
            f"Mapped {len(created)} api-football fixtures for {on.isoformat()} "
            f"({len(ours)} held, {len(theirs)} offered, {ambiguous} ambiguous)"
        )
        return created

    async def _our_fixtures_on(self, on: date) -> List[Fixture]:
        """Fixtures we hold with a kickoff on `on`, give or take the
        tolerance - a match at 23:00 local may be listed on either date."""
        start = _as_datetime(on) - KICKOFF_TOLERANCE
        end = _as_datetime(on) + timedelta(days=1) + KICKOFF_TOLERANCE
        return list(
            (
                await self.session.exec(
                    select(Fixture).where(
                        Fixture.kickoff_at >= start, Fixture.kickoff_at <= end
                    )
                )
            ).all()
        )

    async def _same_fixture(self, ours: Fixture, theirs: NormalizedFixtureRef) -> bool:
        # ensure_utc because the stored value comes back timezone-aware from
        # Postgres and naive from SQLite, and subtracting one from the other
        # raises. The same reason heartbeat.py uses it.
        if abs(ensure_utc(ours.kickoff_at) - theirs.kickoff_at) > KICKOFF_TOLERANCE:
            return False

        home = await self.session.get(Team, ours.home_team_id)
        away = await self.session.get(Team, ours.away_team_id)
        if not home or not away:
            return False

        # Both ends must agree. Matching on one team alone would map a
        # fixture to the wrong opponent whenever a club plays twice in a
        # window.
        return _same_club(home, theirs.home_team_name) and _same_club(
            away, theirs.away_team_name
        )


def _same_club(team: Team, other_name: str) -> bool:
    """Is this our club, under another provider's spelling?

    Tries the registered name, the short name and the curated display name,
    since providers disagree about which they publish - "Brighton" against
    "Brighton & Hove Albion FC" is the case that broke a naive matcher
    before.
    """
    theirs = normalize(other_name)
    if not theirs:
        return False

    for candidate in (team.name, team.short_name, team.display_name):
        if not candidate:
            continue
        ours = normalize(candidate)
        if ours and (
            ours == theirs or ours.startswith(theirs) or theirs.startswith(ours)
        ):
            return True
    return False


def _as_datetime(on: date):
    from datetime import datetime, time, timezone

    return datetime.combine(on, time.min, tzinfo=timezone.utc)


async def resolve_fixture_ref(
    session: AsyncSession, source: str, fixture_id: int
) -> Optional[str]:
    """Whichever id `source` uses for a fixture we hold, if we know it."""
    rows = await IdMapper(session).aliases(EntityType.FIXTURE, fixture_id)
    for row in rows:
        if row.source == source:
            return row.external_id
    return None
