import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ShotEventOut(BaseModel):
    id: uuid.UUID
    fixture_id: int
    team_id: int
    player_name: str
    assist_player_name: Optional[str]
    minute: int
    xg: float
    location_x: float
    location_y: float
    body_part: Optional[str]
    situation: Optional[str]
    result: str

    model_config = ConfigDict(from_attributes=True)


class ShotEventListResponse(BaseModel):
    items: list[ShotEventOut]
    total: int
