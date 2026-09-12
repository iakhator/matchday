from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from app.utils.datetime_utils import utcnow


class League(SQLModel, table=True):
    """A competition/league, normalized across connectors.

    `id` is this gateway's own id. The upstream provider's numeric id lives
    in `external_ids` alongside any other source that knows this
    competition - see that model for why provider ids cannot serve as
    primary keys here.

    One row represents a competition forever; `current_season_year` is
    overwritten in place on each sync rather than the row being recreated.

    `external_ref` stays on the row itself, separately from the mapping,
    because it is the provider's *code* ("PL") rather than its id, and it
    is what the sync methods pass to the upstream API - football-data.org's
    URL paths take the code. Keeping it here avoids a mapping lookup on
    every sync just to build a URL.
    """

    __tablename__: str = "leagues"

    id: Optional[int] = Field(default=None, primary_key=True)
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
