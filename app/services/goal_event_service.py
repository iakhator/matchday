"""Goal events, fetched per fixture from api-football.

Replaces deriving goals from Understat shot data. Same output, but from a
provider that publishes match events on its free plan rather than from a
scraper defeating bot detection - so goals can be served from a hosted
instance, which they could not before.
"""

from typing import List, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.connectors.api_football import ApiFootballConnector, NormalizedGoalEvent
from app.core.logger import logger
from app.db.models import EntityType, Fixture, GoalEvent
from app.services.id_mapper import IdMapper


class GoalEventService:
    def __init__(self, session: AsyncSession, connector: ApiFootballConnector):
        self.session = session
        self.connector = connector
        self.ids = IdMapper(session)

    async def sync_fixture(self, fixture: Fixture) -> int:
        """Fetch and store goals for one finished fixture.

        Returns the number stored. Zero is a legitimate answer - a goalless
        match, or a fixture we have no api-football mapping for.
        """
        fixture_ref = await self._their_fixture_ref(fixture.id)
        if not fixture_ref:
            # No mapping, or only an unverified one. Skipping is right:
            # attaching goals via a guessed mapping puts one match's goals
            # on another, and the first symptom is a nonsensical scoreline.
            logger.debug(
                f"No verified api-football mapping for fixture {fixture.id}, skipping"
            )
            return 0

        events = await self.connector.fetch_goal_events(fixture_ref)
        if not events:
            return 0

        team_ids = await self._team_ids_for(fixture, events)

        stored = 0
        for event in events:
            team_id = team_ids.get(event.team_external_ref)
            if team_id is None:
                # A goal we cannot attribute to a team we hold. Storing it
                # against a guess would be worse than not storing it.
                logger.warning(
                    f"Fixture {fixture.id}: no team for api-football ref "
                    f"{event.team_external_ref}, dropping a {event.kind}"
                )
                continue

            if await self._already_stored(fixture.id, event):
                continue

            self.session.add(
                GoalEvent(
                    fixture_id=fixture.id,
                    team_id=team_id,
                    player_name=event.player_name,
                    assist_player_name=event.assist_player_name,
                    minute=event.minute,
                    kind=event.kind,
                    source=self.connector.source,
                )
            )
            stored += 1

        await self.session.commit()
        if stored:
            logger.info(f"Stored {stored} goal events for fixture {fixture.id}")
            await self._warn_if_score_disagrees(fixture)
        return stored

    async def _warn_if_score_disagrees(self, fixture: Fixture) -> None:
        """Compare the goals we stored against the score we hold.

        Goals come from api-football and the score from football-data.org,
        so this is a free cross-provider check on every sync - and the only
        thing that catches a whole class of quiet corruption. It found the
        bug where "Missed Penalty" was counted as a goal, turning a real
        1-1 into a derived 2-1: no exception, no failed request, just a
        scoreline that had stopped being true.

        A warning rather than a failure. Providers do legitimately disagree
        for a while around a correction, and refusing to store goals
        because of it would lose real data over a temporary mismatch.
        """
        if fixture.home_score is None or fixture.away_score is None:
            return

        goals = (
            await self.session.exec(
                select(GoalEvent).where(GoalEvent.fixture_id == fixture.id)
            )
        ).all()
        derived_home = sum(1 for g in goals if g.team_id == fixture.home_team_id)
        derived_away = sum(1 for g in goals if g.team_id == fixture.away_team_id)

        if (derived_home, derived_away) != (fixture.home_score, fixture.away_score):
            logger.warning(
                f"Fixture {fixture.id}: goal events imply "
                f"{derived_home}-{derived_away} but the recorded score is "
                f"{fixture.home_score}-{fixture.away_score}. One of the two "
                f"providers is wrong, or an event type is being miscounted."
            )

    async def _their_fixture_ref(self, fixture_id: int) -> Optional[str]:
        """api-football's id for a fixture we hold, only if the mapping has
        been confirmed."""
        for row in await self.ids.aliases(EntityType.FIXTURE, fixture_id):
            if row.source == self.connector.source and row.verified:
                return row.external_id
        return None

    async def _team_ids_for(
        self, fixture: Fixture, events: List[NormalizedGoalEvent]
    ) -> dict:
        """Map api-football team refs onto our team ids.

        Only the two clubs in this fixture are considered. api-football
        reports the team a goal COUNTS FOR - an own goal is recorded
        against the beneficiary, not the scorer's side - so no flipping is
        needed here. Understat does the opposite, and carrying that
        convention across would credit every own goal to the wrong team.
        """
        # Only the two clubs in this fixture. Team mappings are written by
        # FixtureMapper alongside each certain fixture match, so if they are
        # absent the fixture mapping was not certain either and the caller
        # will already have skipped.
        mapping = {}
        for team_id in (fixture.home_team_id, fixture.away_team_id):
            for row in await self.ids.aliases(EntityType.TEAM, team_id):
                if row.source == self.connector.source:
                    mapping[row.external_id] = team_id

        return mapping

    async def _already_stored(self, fixture_id: int, event: NormalizedGoalEvent) -> bool:
        """Deduplicated on the natural key, not on a provider id - upstream
        gives events no id, and #16 showed one event can arrive twice."""
        existing = (
            await self.session.exec(
                select(GoalEvent).where(
                    GoalEvent.fixture_id == fixture_id,
                    GoalEvent.minute == event.minute,
                    GoalEvent.player_name == event.player_name,
                    GoalEvent.kind == event.kind,
                )
            )
        ).first()
        return existing is not None
