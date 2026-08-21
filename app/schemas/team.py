from typing import Optional

from pydantic import BaseModel, ConfigDict


class TeamOut(BaseModel):
    id: int
    league_id: int
    season_year: int
    name: str
    short_name: Optional[str]
    code: Optional[str]
    logo: Optional[str]
    venue: Optional[str]

    model_config = ConfigDict(from_attributes=True)
