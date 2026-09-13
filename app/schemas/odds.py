from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class OddsOut(BaseModel):
    """One bookmaker's pre-match prices."""

    bookmaker: str
    home: Optional[float]
    draw: Optional[float]
    away: Optional[float]

    # When these were read. Served because odds move: prices captured a day
    # out and prices captured ten minutes out are both legitimate and mean
    # very different things, and presenting stale ones as current is worse
    # than serving none.
    captured_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OddsListResponse(BaseModel):
    fixture_id: int

    # False means nobody priced this fixture, or it was never captured -
    # and odds cannot be backfilled once a match kicks off, so an empty
    # list here is permanent rather than pending.
    available: bool
    source: Optional[str]
    items: List[OddsOut]
    total: int
