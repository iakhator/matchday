import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel
from uuid6 import uuid7

from app.utils.datetime_utils import utcnow


class TeamMatchStat(SQLModel, table=True):
    """A team's advanced match stats from Understat - non-penalty xG, PPDA
    (pressing intensity), deep completions, expected points. This class of
    metric isn't in api-sports.io at any tier; it's the actual
    differentiator for this connector.
    """

    __tablename__: str = "team_match_stats"

    id: uuid.UUID = Field(default_factory=uuid7, primary_key=True)
    fixture_id: int = Field(foreign_key="fixtures.id", nullable=False)
    team_id: int = Field(foreign_key="teams.id", nullable=False)
    source: str = Field(max_length=50, nullable=False)

    points: int = Field(default=0, nullable=False)
    expected_points: float = Field(default=0, nullable=False)
    goals: int = Field(default=0, nullable=False)
    xg: float = Field(default=0, nullable=False)
    np_xg: float = Field(default=0, nullable=False)
    np_xg_difference: float = Field(default=0, nullable=False)
    ppda: float = Field(default=0, nullable=False)
    deep_completions: int = Field(default=0, nullable=False)

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
            "fixture_id", "team_id", name="uq_team_match_stat_fixture_team"
        ),
    )
