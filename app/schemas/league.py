from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class LeagueOut(BaseModel):
    id: int
    name: str
    country: Optional[str]
    logo: Optional[str]
    current_season_year: Optional[int]
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)
