from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.core.config import settings

api_key_header = APIKeyHeader(name="X-Gateway-Key", auto_error=False)


async def require_api_key(api_key: str = Security(api_key_header)) -> str:
    """Gate access to the gateway's API.

    If GATEWAY_API_KEYS is empty (the default for local dev), auth is
    disabled entirely so self-hosters can get started without any setup.
    Set it in production to restrict who can call your gateway.
    """
    allowed_keys = settings.gateway_api_keys
    if not allowed_keys:
        return "dev"

    if not api_key or api_key not in allowed_keys:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Gateway-Key")

    return api_key
