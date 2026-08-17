import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel
from uuid6 import uuid7

from app.utils.datetime_utils import utcnow


class Team(SQLModel, table=True):
    __tablename__: str = "teams"

    id: uuid.UUID = Field(default_factory=uuid7, primary_key=True)
    league_id: uuid.UUID = Field(foreign_key="leagues.id", nullable=False)
    season_year: int = Field(nullable=False)

    source: str = Field(max_length=50, nullable=False)
    external_ref: str = Field(max_length=50, nullable=False)

    name: str = Field(nullable=False)
    short_name: Optional[str] = Field(default=None)
    code: Optional[str] = Field(default=None, max_length=10)
    logo: Optional[str] = Field(default=None)
    venue: Optional[str] = Field(default=None)

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
            "league_id", "season_year", "source", "external_ref",
            name="uq_team_league_season_source_ref",
        ),
    )
