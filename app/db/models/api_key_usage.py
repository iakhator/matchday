from datetime import date as date_
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel, UniqueConstraint


class ApiKeyUsageDaily(SQLModel, table=True):
    """One row per key per UTC day, incremented on every authenticated
    request - see `app.core.usage`.

    Deliberately not a raw per-request log. A billing period is a SUM over
    a handful of rows instead of a scan over however many requests were
    made, and there is nothing here expensive enough to need a retention
    policy: a year of daily counters for one key is ~365 tiny rows.

    `rate_limit_key` is the same identity the rate limiter already buckets
    by (an env key's name, or a self-serve key's own record id) - one
    counter per key, not a second one that can drift from what the limiter
    thinks a key has used.
    """

    __tablename__: str = "api_key_usage_daily"
    __table_args__ = (
        UniqueConstraint("rate_limit_key", "date", name="uq_usage_daily_key_date"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    rate_limit_key: str = Field(max_length=100, nullable=False, index=True)
    date: date_ = Field(nullable=False, index=True)
    request_count: int = Field(default=0, nullable=False)


class ApiKeyUsageHourly(SQLModel, table=True):
    """One row per key per UTC hour - the recent-traffic view (a usage
    graph, a burst that explains a 429) that the daily table is too coarse
    for. `hour` is always truncated to :00:00.

    Kept only for a short, recent window by design - see `app.core.usage`
    for why this doesn't carry the daily table's "keep forever" property.
    Minute-level would be 60x the rows for a gateway at this project's
    traffic scale, for a graph nobody would read at that resolution.
    """

    __tablename__: str = "api_key_usage_hourly"
    __table_args__ = (
        UniqueConstraint("rate_limit_key", "hour", name="uq_usage_hourly_key_hour"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    rate_limit_key: str = Field(max_length=100, nullable=False, index=True)
    hour: datetime = Field(
        sa_column=sa.Column(sa.DateTime(timezone=True), nullable=False, index=True)
    )
    request_count: int = Field(default=0, nullable=False)
