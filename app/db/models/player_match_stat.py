import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel
from uuid6 import uuid7

from app.utils.datetime_utils import utcnow


class PlayerMatchStat(SQLModel, table=True):
    """A player's advanced stats (xG, xA, xG-chain/buildup) for one match,
    from Understat - data api-sports.io doesn't offer at all. Understat has
    its own player id space, unrelated to football-data.org's - same
    reasoning as PlayerStat, `source` + `external_ref` identifies the
    player within Understat's own identity, not reconciled against
    football-data.org's player ids.
    """

    __tablename__: str = "player_match_stats"

    id: uuid.UUID = Field(default_factory=uuid7, primary_key=True)
    fixture_id: int = Field(foreign_key="fixtures.id", nullable=False)
    team_id: int = Field(foreign_key="teams.id", nullable=False)

    source: str = Field(max_length=50, nullable=False)
    external_ref: str = Field(max_length=50, nullable=False)

    player_name: str = Field(nullable=False)
    position: Optional[str] = Field(default=None, max_length=20)

    minutes: int = Field(default=0, nullable=False)
    goals: int = Field(default=0, nullable=False)
    own_goals: int = Field(default=0, nullable=False)
    shots: int = Field(default=0, nullable=False)
    xg: float = Field(default=0, nullable=False)
    xg_chain: float = Field(default=0, nullable=False)
    xg_buildup: float = Field(default=0, nullable=False)
    assists: int = Field(default=0, nullable=False)
    xa: float = Field(default=0, nullable=False)
    key_passes: int = Field(default=0, nullable=False)
    yellow_cards: int = Field(default=0, nullable=False)
    red_cards: int = Field(default=0, nullable=False)

    created_at: Optional[datetime] = Field(
        default_factory=utcnow, sa_column=sa.Column(sa.DateTime(timezone=True))
    )
    updated_at: Optional[datetime] = Field(
        default_factory=utcnow,
        sa_column=sa.Column(
            sa.DateTime(timezone=True), default=utcnow, onupdate=utcnow
        ),
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "fixture_id", "source", "external_ref",
            name="uq_player_match_stat_fixture_source_ref",
        ),
    )
