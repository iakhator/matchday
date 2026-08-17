import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict


class TeamOut(BaseModel):
    id: uuid.UUID
    league_id: uuid.UUID
    season_year: int
    name: str
    short_name: Optional[str]
    code: Optional[str]
    logo: Optional[str]
    venue: Optional[str]

    model_config = ConfigDict(from_attributes=True)
