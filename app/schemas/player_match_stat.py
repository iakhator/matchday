import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict


class PlayerMatchStatOut(BaseModel):
    id: uuid.UUID
    fixture_id: int
    team_id: int
    player_name: str
    position: Optional[str]
    minutes: int
    goals: int
    own_goals: int
    shots: int
    xg: float
    xg_chain: float
    xg_buildup: float
    assists: int
    xa: float
    key_passes: int
    yellow_cards: int
    red_cards: int

    model_config = ConfigDict(from_attributes=True)


class PlayerMatchStatListResponse(BaseModel):
    items: list[PlayerMatchStatOut]
    total: int
