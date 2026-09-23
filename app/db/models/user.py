import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel
from uuid6 import uuid7

from app.utils.datetime_utils import utcnow


class User(SQLModel, table=True):
    """A human who has signed in with Firebase to manage their own API keys.

    Identity only - Firebase is the source of truth for "who is this
    person" (email, password, session). This row exists purely so
    ApiKeyRecord has something stable to own a key against, decoupled from
    Firebase's own uid format.
    """

    __tablename__: str = "users"

    id: uuid.UUID = Field(default_factory=uuid7, primary_key=True)
    firebase_uid: str = Field(max_length=128, nullable=False, unique=True, index=True)
    email: str = Field(max_length=255, nullable=False, index=True)
    created_at: Optional[datetime] = Field(
        default_factory=utcnow, sa_column=sa.Column(sa.DateTime(timezone=True))
    )
