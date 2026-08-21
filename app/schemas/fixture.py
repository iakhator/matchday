from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.schemas.team import TeamOut


class FixtureOut(BaseModel):
    id: int
    league_id: int
    season_year: int
    matchday: Optional[int]
    home_team: TeamOut
    away_team: TeamOut
    kickoff_at: datetime
    status: str
    home_score: Optional[int]
    away_score: Optional[int]
    last_synced_at: Optional[datetime]


class FixtureListResponse(BaseModel):
    items: list[FixtureOut]
    total: int
