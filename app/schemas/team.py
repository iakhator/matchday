from typing import Optional

from pydantic import BaseModel, ConfigDict


class TeamOut(BaseModel):
    id: int
    league_id: int
    season_year: int
    name: str

    # As upstream sent it, untouched - so a consumer can always see what
    # the source actually said and reconcile against it.
    short_name: Optional[str]

    # What to render. Resolved at sync time from app/core/display_names.py,
    # and differs from short_name only where upstream sends a nickname
    # ("Atleti" -> "Atlético Madrid").
    display_name: Optional[str]

    code: Optional[str]
    logo: Optional[str]
    venue: Optional[str]

    model_config = ConfigDict(from_attributes=True)
