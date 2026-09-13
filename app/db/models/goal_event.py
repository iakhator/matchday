import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel
from uuid6 import uuid7

from app.utils.datetime_utils import utcnow


class GoalEvent(SQLModel, table=True):
    """A goal, as reported by a provider that publishes match events.

    Replaces deriving goals from Understat shot data. That worked, but it
    meant goal events depended on a scraper reaching its source through a
    spoofed TLS handshake - fragile, and the one thing in this codebase
    that could not be served from a hosted instance. api-football carries
    real goal events on its free plan, so goals become ordinary licensed
    data and Understat is left carrying only xG and shot maps, which are
    genuinely extra rather than load-bearing.
    """

    __tablename__: str = "goal_events"
    __table_args__ = (
        # Providers occasionally emit the same event twice, and upstream
        # gives events no id of their own to deduplicate on - so the key is
        # what the goal IS. Verified against real data in #16, where one
        # fixture's goals were each stored twice and the derived score came
        # out at double the real one.
        sa.UniqueConstraint(
            "fixture_id", "minute", "player_name", "kind",
            name="uq_goal_events_natural",
        ),
        sa.Index("ix_goal_events_fixture", "fixture_id"),
    )

    id: uuid.UUID = Field(default_factory=uuid7, primary_key=True)

    fixture_id: int = Field(foreign_key="fixtures.id", nullable=False)

    # The team the goal COUNTS FOR, which is what api-football publishes -
    # an own goal is recorded against the team that benefits, not the
    # scorer's. Understat does the opposite, and carrying its convention
    # over would credit every own goal to the wrong side. Verified against
    # a real 4-0 where all four goals, including an own goal by an away
    # player, are recorded under the home team.
    team_id: int = Field(foreign_key="teams.id", nullable=False)

    player_name: str = Field(nullable=False)
    assist_player_name: Optional[str] = Field(default=None)
    minute: int = Field(nullable=False)

    # "goal" | "own_goal" | "penalty". Kept because a consumer rendering a
    # scorer list needs to mark an own goal differently, and because a
    # penalty is worth distinguishing for anything computing form.
    kind: str = Field(default="goal", max_length=20, nullable=False)

    source: str = Field(max_length=50, nullable=False)

    created_at: Optional[datetime] = Field(
        default_factory=utcnow, sa_column=sa.Column(sa.DateTime(timezone=True))
    )
