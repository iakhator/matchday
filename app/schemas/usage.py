import uuid
from datetime import datetime

from pydantic import BaseModel


class HourlyUsageOut(BaseModel):
    hour: datetime
    count: int


class KeyUsageOut(BaseModel):
    key_id: uuid.UUID
    name: str
    requests_today: int
    requests_this_month: int
    # Last 24 hours, oldest first, zero-filled for hours with no traffic -
    # a continuous series a chart can plot directly.
    hourly: list[HourlyUsageOut]


class UsageResponse(BaseModel):
    items: list[KeyUsageOut]
