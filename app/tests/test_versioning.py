"""The version contract, and the mechanics for changing it.

What this API sells is that code written against /api/v1 keeps working.
These cover the two things that make that checkable from the outside: every
response says which contract served it, and anything being retired says so
in headers a machine can act on.
"""

from datetime import date

import pytest
from fastapi import APIRouter, Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.versioning import (
    API_VERSION,
    VERSION_HEADER,
    add_version_header,
    deprecated,
)

pytestmark = pytest.mark.asyncio

SUNSET = date(2027, 1, 1)


@pytest.fixture
async def client():
    router = APIRouter(prefix="/api/v1", dependencies=[Depends(add_version_header)])

    @router.get("/current")
    async def current():
        return {"ok": True}

    @router.get(
        "/old",
        dependencies=[deprecated(SUNSET, successor="/api/v1/current")],
    )
    async def old():
        return {"ok": True}

    @router.get("/old-no-successor", dependencies=[deprecated(SUNSET)])
    async def old_no_successor():
        return {"ok": True}

    app = FastAPI()
    app.include_router(router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


class TestVersionHeader:
    async def test_every_response_states_its_version(self, client):
        """So a consumer reading a captured response can tell which contract
        produced it, without reconstructing the URL that was called."""
        response = await client.get("/api/v1/current")
        assert response.headers[VERSION_HEADER] == API_VERSION

    async def test_the_header_is_applied_at_the_router(self, client):
        """Applied to the router rather than each route, so a new endpoint
        cannot be added without it."""
        for path in ("/api/v1/current", "/api/v1/old"):
            assert (await client.get(path)).headers[VERSION_HEADER] == API_VERSION


class TestDeprecation:
    async def test_a_live_endpoint_is_not_marked_deprecated(self, client):
        response = await client.get("/api/v1/current")
        assert "Deprecation" not in response.headers
        assert "Sunset" not in response.headers

    async def test_deprecated_endpoint_announces_itself(self, client):
        response = await client.get("/api/v1/old")
        assert response.headers["Deprecation"] == "true"
        assert "Sunset" in response.headers

    async def test_sunset_is_an_http_date(self, client):
        """RFC 8594 wants an HTTP-date, not an ISO one - a consumer parsing
        it with a standard library helper should not have to special case
        us."""
        from email.utils import parsedate_to_datetime

        sunset = (await client.get("/api/v1/old")).headers["Sunset"]
        assert parsedate_to_datetime(sunset).date() == SUNSET

    async def test_successor_is_advertised(self, client):
        """Telling someone an endpoint is going away without saying what
        replaces it leaves them reading a changelog to find out."""
        link = (await client.get("/api/v1/old")).headers["Link"]
        assert 'rel="successor-version"' in link
        assert "/api/v1/current" in link

    async def test_successor_is_optional(self, client):
        """Some things are retired with nothing replacing them."""
        response = await client.get("/api/v1/old-no-successor")
        assert response.headers["Deprecation"] == "true"
        assert "Link" not in response.headers

    async def test_a_deprecated_endpoint_still_works(self, client):
        """Deprecated means "going away", not "already gone". Breaking it at
        announcement would defeat the notice period entirely."""
        response = await client.get("/api/v1/old")
        assert response.status_code == 200
        assert response.json() == {"ok": True}
