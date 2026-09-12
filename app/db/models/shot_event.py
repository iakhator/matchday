import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel
from uuid6 import uuid7

from app.utils.datetime_utils import utcnow


class ShotEvent(SQLModel, table=True):
    """A single shot from Understat, with location coordinates and xG -
    shot-map quality data api-sports.io doesn't provide at all.
    """

    __tablename__: str = "shot_events"

    id: uuid.UUID = Field(default_factory=uuid7, primary_key=True)
    fixture_id: int = Field(foreign_key="fixtures.id", nullable=False)
    team_id: int = Field(foreign_key="teams.id", nullable=False)

    source: str = Field(max_length=50, nullable=False)
    external_ref: str = Field(max_length=50, nullable=False)

    player_name: str = Field(nullable=False)
    assist_player_name: Optional[str] = Field(default=None)
    minute: int = Field(nullable=False)
    xg: float = Field(nullable=False)
    location_x: float = Field(nullable=False)
    location_y: float = Field(nullable=False)
    body_part: Optional[str] = Field(default=None, max_length=20)
    situation: Optional[str] = Field(default=None, max_length=30)
    result: str = Field(max_length=30, nullable=False)

    created_at: Optional[datetime] = Field(
        default_factory=utcnow, sa_column=sa.Column(sa.DateTime(timezone=True))
    )

    __table_args__ = (
        sa.UniqueConstraint(
            "source", "external_ref", name="uq_shot_event_source_ref"
        ),
    )
