import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class PlayerStatOut(BaseModel):
    id: uuid.UUID
    team_id: uuid.UUID
    season_year: int
    name: str
    photo: Optional[str]
    position: Optional[str]
    goals: int
    assists: int
    appearances: int
    last_synced_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class PlayerStatListResponse(BaseModel):
    items: list[PlayerStatOut]
    total: int
