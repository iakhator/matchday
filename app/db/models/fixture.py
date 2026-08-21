from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from app.utils.datetime_utils import utcnow

# Normalized status values every connector must map its provider-specific
# status strings onto. Consumers of this gateway only ever see these.
FIXTURE_STATUSES = (
    "scheduled",
    "live",
    "finished",
    "postponed",
    "suspended",
    "cancelled",
)


class Fixture(SQLModel, table=True):
    """A single match. `id` is the provider's own stable numeric match id
    (e.g. football-data.org's fixture id) - same reasoning as League/Team,
    see those models' docstrings.
    """

    __tablename__: str = "fixtures"

    id: int = Field(primary_key=True)
    league_id: int = Field(foreign_key="leagues.id", nullable=False)
    season_year: int = Field(nullable=False)
    matchday: Optional[int] = Field(default=None, index=True)
    source: str = Field(max_length=50, nullable=False)

    home_team_id: int = Field(foreign_key="teams.id", nullable=False)
    away_team_id: int = Field(foreign_key="teams.id", nullable=False)

    kickoff_at: datetime = Field(
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False)
    )
    status: str = Field(max_length=20, nullable=False, index=True)
    raw_status: Optional[str] = Field(default=None, max_length=50)

    home_score: Optional[int] = Field(default=None)
    away_score: Optional[int] = Field(default=None)

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
