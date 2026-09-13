"""Capturing pre-match odds.

The whole shape of this is set by one fact: **odds cannot be backfilled.**
Upstream serves them only while a fixture is upcoming, so a capture that
does not happen before kickoff is a permanent hole. Everything else in this
gateway can be repaired by re-syncing; this cannot.

So the job is deliberately eager rather than precise. It captures anything
kicking off within the window, re-captures as kickoff approaches because
prices move, and reports what it could not reach instead of finishing
quietly.
"""

from datetime import timedelta
from typing import List, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors.api_football import ApiFootballConnector, DailyBudgetExceeded
from app.core.logger import logger
from app.db.models import EntityType, Fixture, Odds
from app.services.id_mapper import IdMapper
from app.utils.datetime_utils import ensure_utc, utcnow

# How far ahead of kickoff to start capturing. Long enough that a single
# missed scheduler run is not fatal - the next one still has time - and
# short enough that prices are meaningful rather than opening lines.
CAPTURE_WINDOW = timedelta(hours=24)


class OddsService:
    def __init__(self, session: AsyncSession, connector: ApiFootballConnector):
        self.session = session
        self.connector = connector
        self.ids = IdMapper(session)

    async def capture_upcoming(self) -> dict:
        """Capture odds for every fixture kicking off soon.

        Returns a summary rather than a count, because "how many did we
        get" is the less useful half. The half that matters is what we
        missed and why - those are the permanent holes.
        """
        fixtures = await self._fixtures_in_window()
        captured, unmapped, unavailable = 0, 0, 0

        for fixture in fixtures:
            fixture_ref = await self._their_fixture_ref(fixture.id)
            if not fixture_ref:
                unmapped += 1
                continue

            try:
                rows = await self.connector.fetch_odds(fixture_ref)
            except DailyBudgetExceeded:
                # Stop rather than grind through the remaining fixtures
                # collecting failures. The ones not reached are reported
                # below, which is the signal worth having.
                logger.error(
                    f"Odds capture stopped early: api-football budget spent. "
                    f"{len(fixtures) - captured - unmapped - unavailable} "
                    f"fixture(s) not captured, and odds cannot be backfilled."
                )
                break

            if not rows:
                unavailable += 1
                continue

            for row in rows:
                await self._store(fixture.id, row)
            captured += 1

        await self.session.commit()

        summary = {
            "fixtures_in_window": len(fixtures),
            "captured": captured,
            "unmapped": unmapped,
            "no_odds_offered": unavailable,
        }
        if unmapped:
            # Worth a warning, not a debug line: an unmapped fixture means
            # its odds will never exist, and the fix (reviewing the
            # mapping) has a deadline of kickoff.
            logger.warning(
                f"{unmapped} fixture(s) in the odds window have no verified "
                f"api-football mapping - their odds cannot be captured, and "
                f"cannot be recovered after kickoff."
            )
        logger.info(f"Odds capture: {summary}")
        return summary

    async def _fixtures_in_window(self) -> List[Fixture]:
        now = utcnow()
        return list(
            (
                await self.session.exec(
                    select(Fixture).where(
                        Fixture.kickoff_at > now,
                        Fixture.kickoff_at <= now + CAPTURE_WINDOW,
                    )
                )
            ).all()
        )

    async def _their_fixture_ref(self, fixture_id: int) -> Optional[str]:
        for row in await self.ids.aliases(EntityType.FIXTURE, fixture_id):
            if row.source == self.connector.source and row.verified:
                return row.external_id
        return None

    async def _store(self, fixture_id: int, row) -> None:
        """Upsert one bookmaker's prices.

        Updated in place rather than appended. Prices move, and the current
        ones are what a consumer asks for - keeping every observation would
        be a price-history feature, which is a different thing and would
        make this the largest table here within a season.
        """
        existing = (
            await self.session.exec(
                select(Odds).where(
                    Odds.fixture_id == fixture_id, Odds.bookmaker == row.bookmaker
                )
            )
        ).first()

        if existing:
            existing.home, existing.draw, existing.away = row.home, row.draw, row.away
            existing.captured_at = utcnow()
            self.session.add(existing)
            return

        self.session.add(
            Odds(
                fixture_id=fixture_id,
                bookmaker=row.bookmaker,
                home=row.home,
                draw=row.draw,
                away=row.away,
                source=self.connector.source,
                captured_at=utcnow(),
            )
        )


def staleness_seconds(odds: Odds, kickoff_at) -> int:
    """How long before kickoff these prices were read.

    Served alongside the odds so a consumer can judge them. Prices captured
    23 hours out and prices captured 10 minutes out are both legitimate and
    mean very different things.
    """
    return max(
        0, int((ensure_utc(kickoff_at) - ensure_utc(odds.captured_at)).total_seconds())
    )
