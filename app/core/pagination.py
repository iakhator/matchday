from dataclasses import dataclass

from fastapi import Query

# One contract for every list endpoint that can grow without bound (across
# fixtures, standings and player-stats) - documented once in
# site/guide/pagination.md rather than repeated on every reference page.
DEFAULT_LIMIT = 50
MAX_LIMIT = 100


@dataclass(frozen=True)
class Pagination:
    limit: int
    offset: int


def pagination_params(
    limit: int = Query(
        DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="Max items to return"
    ),
    offset: int = Query(0, ge=0, description="Items to skip, for the next page"),
) -> Pagination:
    return Pagination(limit=limit, offset=offset)
