from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from app.utils.datetime_utils import utcnow


class League(SQLModel, table=True):
    """A competition/league, normalized across connectors.

    `id` is the provider's own stable numeric identifier (e.g.
    football-data.org's competition id, 2021 for the Premier League) - not
    a synthetic key. Confirmed this id never changes across seasons, so one
    row represents a competition forever; `current_season_year` is just
    overwritten in place on each sync rather than the row being recreated.

    `external_ref` is kept separately because it's the provider's *code*
    (e.g. "PL"), not the numeric id - that's what every sync method uses to
    call the upstream API, since football-data.org's URL paths take the
    code, not the numeric id.
    """

    __tablename__: str = "leagues"

    id: int = Field(primary_key=True)
    source: str = Field(max_length=50, nullable=False)
    external_ref: str = Field(max_length=50, nullable=False, index=True)

    name: str = Field(nullable=False)
    country: Optional[str] = Field(default=None)
    logo: Optional[str] = Field(default=None)
    current_season_year: Optional[int] = Field(default=None)

    created_at: Optional[datetime] = Field(
        default_factory=utcnow, sa_column=sa.Column(sa.DateTime(timezone=True))
    )
    updated_at: Optional[datetime] = Field(
        default_factory=utcnow,
        sa_column=sa.Column(
            sa.DateTime(timezone=True), default=utcnow, onupdate=utcnow
        ),
    )
