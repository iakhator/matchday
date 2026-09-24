import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ApiKeyCreatedOut(BaseModel):
    """Returned exactly once, at creation. `secret` never appears in any
    other response - list/get only ever return `key_prefix`."""

    id: uuid.UUID
    name: str
    key_prefix: str
    secret: str
    requests_per_minute: int
    created_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    requests_per_minute: int
    created_at: Optional[datetime]
    last_used_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class ApiKeyListResponse(BaseModel):
    items: list[ApiKeyOut]
    total: int
