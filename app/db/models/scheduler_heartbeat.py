from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from app.utils.datetime_utils import utcnow


class SchedulerHeartbeat(SQLModel, table=True):
    """One row per scheduled job, stamped with its last successful run.

    DB-backed rather than Redis-backed - this repo has no Redis of its own
    (Predify's is reachable over the shared docker network, but coupling
    this gateway's own health check to another app's infra would break the
    "self-hosted, runs standalone" premise this whole project is built on).
    `/health` (see app/main.py) compares `last_run_at` against each job's
    own sync interval plus a grace period to decide staleness.
    """

    __tablename__: str = "scheduler_heartbeats"

    job_id: str = Field(primary_key=True, max_length=50)
    last_run_at: datetime = Field(
        default_factory=utcnow, sa_column=sa.Column(sa.DateTime(timezone=True))
    )
