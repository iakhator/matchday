from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from app.utils.datetime_utils import utcnow


class Team(SQLModel, table=True):
    """A real-world club, normalized across connectors.

    `id` is the provider's own stable numeric identifier (e.g.
    football-data.org's team id, 57 for Arsenal FC) - confirmed this never
    changes across seasons or even across leagues (survives promotion/
    relegation), so one row represents a club forever.

    `league_id`/`season_year` are deliberately NOT part of this row's
    identity - they're just this team's *current* league and season,
    overwritten in place on every sync the same way League.
    current_season_year already works. A club moving up/down a division
    updates these two fields rather than creating a new Team row. Anything
    that's genuinely season-specific (standings, fixtures, player stats)
    already carries its own season_year and points at this stable id.
    """

    __tablename__: str = "teams"

    id: int = Field(primary_key=True)
    source: str = Field(max_length=50, nullable=False)
    league_id: int = Field(foreign_key="leagues.id", nullable=False)
    season_year: int = Field(nullable=False)

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
