import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel
from uuid6 import uuid7

from app.utils.datetime_utils import utcnow


class League(SQLModel, table=True):
    """A competition/league, normalized across connectors.

    `source` + `external_ref` identifies where this row came from and what
    ID that connector uses internally (e.g. source="football_data_org",
    external_ref="PL"). Everything downstream only ever sees this table's
    own `id` - connector identity is an implementation detail.
    """

    __tablename__: str = "leagues"

    id: uuid.UUID = Field(default_factory=uuid7, primary_key=True)
    source: str = Field(max_length=50, nullable=False)
    external_ref: str = Field(max_length=50, nullable=False)

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

    __table_args__ = (
        sa.UniqueConstraint("source", "external_ref", name="uq_league_source_ref"),
    )
