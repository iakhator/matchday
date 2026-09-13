from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from app.utils.datetime_utils import utcnow


class Team(SQLModel, table=True):
    """A real-world club, normalized across connectors.

    `id` is this gateway's own id, not the upstream provider's. Provider
    ids live in `external_ids`, one row per source that knows this club,
    because two providers do not agree on which number means Arsenal - and
    a consumer should not have to care which source answered.

    One club is one row forever. `league_id`/`season_year` are deliberately
    NOT part of this row's identity - they are just its *current* league
    and season, overwritten in place on each sync. A club moving up or down
    a division updates those two fields rather than creating a new row.
    Anything genuinely season-specific (standings, fixtures, player stats)
    carries its own season_year and points at this stable id.

    `source` records which connector last wrote this row. It is provenance,
    not identity - the mapping in `external_ids` is what identifies.
    """

    __tablename__: str = "teams"

    id: Optional[int] = Field(default=None, primary_key=True)
    source: str = Field(max_length=50, nullable=False)
    league_id: int = Field(foreign_key="leagues.id", nullable=False)
    season_year: int = Field(nullable=False)

    name: str = Field(nullable=False)

    # As upstream sent it. Never overwritten, so the row can always be
    # reconciled against the source.
    short_name: Optional[str] = Field(default=None)

    # What to put in front of a user, resolved on write from
    # app/core/display_names.py. Stored rather than computed so it can be
    # searched, sorted and filtered on, and so anything else reading this
    # database - admin tooling, a support query - sees the same name the
    # API serves.
    display_name: Optional[str] = Field(default=None, index=True)
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
