import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel
from uuid6 import uuid7

from app.utils.datetime_utils import utcnow


class PlayerStat(SQLModel, table=True):
    """A player's season-long stats for one team, normalized across
    connectors. Deliberately season totals, not per-fixture - consumers
    that want a "hot player" pick don't need the extra per-fixture API
    cost that a rolling window would require.

    `source` + `external_ref` identifies the player themselves (a provider's
    person ID), separate from `team_id`/`season_year` which scope the stat
    row - the same player could appear under a different team_id if
    transferred mid-season.
    """

    __tablename__: str = "player_stats"

    id: uuid.UUID = Field(default_factory=uuid7, primary_key=True)
    team_id: int = Field(foreign_key="teams.id", nullable=False)
    season_year: int = Field(nullable=False)

    source: str = Field(max_length=50, nullable=False)
    external_ref: str = Field(max_length=50, nullable=False)

    name: str = Field(nullable=False)
    photo: Optional[str] = Field(default=None)
    position: Optional[str] = Field(default=None, max_length=30)

    goals: int = Field(default=0, nullable=False)
    assists: int = Field(default=0, nullable=False)
    appearances: int = Field(default=0, nullable=False)

    last_synced_at: Optional[datetime] = Field(
        default_factory=utcnow, sa_column=sa.Column(sa.DateTime(timezone=True))
    )
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
            "team_id", "season_year", "source", "external_ref",
            name="uq_player_stat_team_season_source_ref",
        ),
    )
