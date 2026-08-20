import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel
from uuid6 import uuid7

from app.utils.datetime_utils import utcnow


class Standing(SQLModel, table=True):
    """A team's current league-table row for one season, normalized across
    connectors the same way Fixture/Team are. Synced from the provider's own
    standings endpoint rather than derived from stored fixtures - that
    endpoint already accounts for points deductions and tiebreaker rules a
    naive win/draw/loss calculation would get wrong.
    """

    __tablename__: str = "standings"

    id: uuid.UUID = Field(default_factory=uuid7, primary_key=True)
    league_id: uuid.UUID = Field(foreign_key="leagues.id", nullable=False)
    team_id: uuid.UUID = Field(foreign_key="teams.id", nullable=False)
    season_year: int = Field(nullable=False)

    rank: int = Field(nullable=False)
    points: int = Field(nullable=False)
    played: int = Field(nullable=False)
    won: int = Field(nullable=False)
    drawn: int = Field(nullable=False)
    lost: int = Field(nullable=False)
    goals_for: int = Field(nullable=False)
    goals_against: int = Field(nullable=False)
    form: Optional[str] = Field(default=None, max_length=20)

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
            "league_id", "season_year", "team_id", name="uq_standing_league_season_team"
        ),
    )
