from datetime import datetime, timezone


def utcnow() -> datetime:
    """Always-timezone-aware UTC now. Pair every datetime column with
    sa_column=Column(DateTime(timezone=True)) or Postgres silently stores
    it as a naive TIMESTAMP and comparisons against this will raise.
    """
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
