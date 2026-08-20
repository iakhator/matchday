import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.schemas.team import TeamOut


class StandingOut(BaseModel):
    id: uuid.UUID
    league_id: uuid.UUID
    season_year: int
    team: TeamOut
    rank: int
    points: int
    played: int
    won: int
    drawn: int
    lost: int
    goals_for: int
    goals_against: int
    form: Optional[str]
    last_synced_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class StandingListResponse(BaseModel):
    items: list[StandingOut]
    total: int
