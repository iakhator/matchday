import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel
from uuid6 import uuid7

from app.utils.datetime_utils import utcnow


class ApiKeyRecord(SQLModel, table=True):
    """A self-serve API key, owned by a User.

    Only a SHA-256 hash of the secret is ever stored - the plaintext is
    returned once, at creation, and never again (same contract as a GitHub
    PAT or a Stripe key). `key_prefix` is what the owner sees afterward to
    tell their keys apart without being able to reconstruct the secret from
    it.

    Revocation deletes the row. An earlier version soft-deleted (a
    `revoked_at` timestamp, row kept for its `last_used_at` history) -
    dropped in favor of an actually self-healing table: a self-serve
    account revoking and regenerating keys repeatedly should not leave a
    permanently growing pile of dead rows behind, and a dashboard
    listing keys the owner can no longer do anything about (not usable,
    not un-revocable) was clutter, not an audit trail worth the cost.
    """

    __tablename__: str = "api_keys"

    id: uuid.UUID = Field(default_factory=uuid7, primary_key=True)
    owner_user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False, index=True)

    name: str = Field(max_length=100, nullable=False)
    key_prefix: str = Field(max_length=16, nullable=False)
    hashed_secret: str = Field(max_length=64, nullable=False, unique=True, index=True)
    requests_per_minute: int = Field(nullable=False)

    created_at: Optional[datetime] = Field(
        default_factory=utcnow, sa_column=sa.Column(sa.DateTime(timezone=True))
    )
    last_used_at: Optional[datetime] = Field(
        default=None, sa_column=sa.Column(sa.DateTime(timezone=True))
    )
