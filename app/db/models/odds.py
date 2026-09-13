import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel
from uuid6 import uuid7

from app.utils.datetime_utils import utcnow


class Odds(SQLModel, table=True):
    """Pre-match 1X2 prices for a fixture, one row per bookmaker.

    Unlike everything else in this schema, odds are **not** re-fetchable.
    Upstream serves them only while a fixture is still upcoming - a
    finished fixture returns nothing, verified against a real one. Miss the
    capture window and those prices are gone permanently; there is no
    re-sync that recovers them.

    That makes this the first table here that is not purely a cache, and it
    has two consequences. A missed capture has to be visible rather than
    silent, since nothing downstream will ever heal it. And `captured_at`
    is part of the data, not metadata: prices move, and a consumer needs to
    know how old the ones it is reading are.
    """

    __tablename__: str = "odds"
    __table_args__ = (
        # One row per bookmaker per fixture. Re-running the capture updates
        # prices in place rather than accumulating a history - a history is
        # a different feature, and storing one by accident is how a table
        # quietly becomes the largest in the database.
        sa.UniqueConstraint("fixture_id", "bookmaker", name="uq_odds_fixture_bookmaker"),
        sa.Index("ix_odds_fixture", "fixture_id"),
    )

    id: uuid.UUID = Field(default_factory=uuid7, primary_key=True)

    fixture_id: int = Field(foreign_key="fixtures.id", nullable=False)
    bookmaker: str = Field(max_length=100, nullable=False)

    # Nullable individually: a bookmaker can price two outcomes and not the
    # third, and losing the whole row over one missing price would be worse
    # than serving a partial one.
    home: Optional[float] = Field(default=None)
    draw: Optional[float] = Field(default=None)
    away: Optional[float] = Field(default=None)

    source: str = Field(max_length=50, nullable=False)

    # When these prices were read, not when the row was written. Odds
    # presented as current when they are six hours old are worse than no
    # odds at all, so this travels with them through the API.
    captured_at: datetime = Field(
        default_factory=utcnow,
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False),
    )
    updated_at: Optional[datetime] = Field(
        default_factory=utcnow,
        sa_column=sa.Column(
            sa.DateTime(timezone=True), default=utcnow, onupdate=utcnow
        ),
    )
