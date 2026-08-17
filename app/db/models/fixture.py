import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel
from uuid6 import uuid7

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
    __tablename__: str = "fixtures"

    id: uuid.UUID = Field(default_factory=uuid7, primary_key=True)
    league_id: uuid.UUID = Field(foreign_key="leagues.id", nullable=False)
    season_year: int = Field(nullable=False)
    matchday: Optional[int] = Field(default=None, index=True)

    source: str = Field(max_length=50, nullable=False)
    external_ref: str = Field(max_length=50, nullable=False)

    home_team_id: uuid.UUID = Field(foreign_key="teams.id", nullable=False)
    away_team_id: uuid.UUID = Field(foreign_key="teams.id", nullable=False)

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

    __table_args__ = (
        sa.UniqueConstraint("source", "external_ref", name="uq_fixture_source_ref"),
    )
