"""API versioning and deprecation.

The thing this API sells is a contract: a consumer writes code against
`/api/v1`, and that code keeps working. Everything else - which upstream
provider answered, what the schema looks like underneath, which connector
is registered - is deliberately invisible to them and free to change.

A policy with no way to execute it is just a paragraph, so the deprecation
headers live here. Nothing is deprecated today; this exists so that when
something is, the announcement is machine-readable from the first day
rather than a note in a changelog nobody parses.

See the README, "API versioning and stability", for the promise itself.
"""

from datetime import date, datetime, time, timezone
from email.utils import format_datetime
from typing import Optional

from fastapi import Depends, Response

# The version this build serves. Bumped only for a breaking change, which
# by policy means a new path (`/api/v2`) served alongside the old one -
# never a change in place.
API_VERSION = "v1"

VERSION_HEADER = "X-API-Version"


async def add_version_header(response: Response) -> None:
    """Stamp every response with the contract it was served under.

    Lets a consumer log or assert the version without parsing it back out
    of the URL they called - which matters most when something has gone
    wrong and they are reading a captured response rather than making a
    new one.
    """
    response.headers[VERSION_HEADER] = API_VERSION


def deprecated(sunset: date, successor: Optional[str] = None):
    """Mark an endpoint as going away, in a form machines can read.

    Emits RFC 8594 `Sunset` and a `Deprecation` header, plus a `Link` to
    whatever replaces it. A consumer can then alert on the header in CI or
    in their own logging, instead of finding out when the endpoint stops
    answering.

    Usage:

        @router.get("/old", dependencies=[deprecated(date(2027, 1, 1),
                                                     successor="/api/v1/new")])

    The date is required and deliberately has no default. A deprecation
    without a date is a wish, and consumers cannot schedule work against
    it.
    """
    # RFC 8594 wants an HTTP-date. Midnight UTC on the stated day, so the
    # endpoint is answered for the whole of its last day.
    sunset_at = datetime.combine(sunset, time.min, tzinfo=timezone.utc)
    sunset_header = format_datetime(sunset_at, usegmt=True)

    async def _mark(response: Response) -> None:
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = sunset_header
        if successor:
            response.headers["Link"] = f'<{successor}>; rel="successor-version"'

    return Depends(_mark)
