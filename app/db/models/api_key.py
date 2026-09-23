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

    Revocation is a timestamp, not a delete - keeping the row lets
    `last_used_at` survive revoking a key, and means a revoked key's
    identity can never be reissued the way reusing a deleted row's slot
    could.
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
    revoked_at: Optional[datetime] = Field(
        default=None, sa_column=sa.Column(sa.DateTime(timezone=True))
    )
