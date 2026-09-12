from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.api_keys import ApiKey
from app.core.auth import require_api_key
from app.db.database import get_session
from app.db.models import EntityType
from app.schemas.lookup import AliasesOut, AliasOut, LookupOut
from app.services.id_mapper import IdMapper

router = APIRouter(prefix="/lookup", tags=["lookup"])

# Kept as an explicit allow-list rather than accepting any string, so a
# typo gets a 400 naming the valid options instead of an empty result that
# looks like "none of your ids are known".
ENTITY_TYPES = {EntityType.LEAGUE, EntityType.TEAM, EntityType.FIXTURE}

# Enough for a full season's fixtures in one call, bounded so a single
# request cannot ask the database for an unbounded IN list.
MAX_REFS = 500


def _validate_entity_type(entity_type: str) -> str:
    if entity_type not in ENTITY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown entity_type. Expected one of: {sorted(ENTITY_TYPES)}",
        )
    return entity_type


@router.get("/{entity_type}", response_model=LookupOut)
async def lookup(
    entity_type: str,
    source: str = Query(..., description="Which provider the ids belong to"),
    external_id: str = Query(
        ...,
        description="Provider id, or several separated by commas",
    ),
    session: AsyncSession = Depends(get_session),
    _: ApiKey = Depends(require_api_key),
):
    """Translate another provider's ids into this gateway's.

    Exists so a consumer already keyed to a different provider can adopt
    gateway ids gradually instead of re-keying its history in one step:
    ask which gateway row is api-sports' team 57, store that, and migrate
    at its own pace.

    Batched deliberately. Matching a season of fixtures one request at a
    time is hundreds of round trips against a rate-limited API, and the
    consumers most likely to need this are doing exactly that.
    """
    _validate_entity_type(entity_type)

    refs = [r.strip() for r in external_id.split(",") if r.strip()]
    if not refs:
        raise HTTPException(status_code=400, detail="No external_id values given")
    if len(refs) > MAX_REFS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many ids in one request (max {MAX_REFS}, got {len(refs)})",
        )

    resolved = await IdMapper(session).resolve_many(entity_type, source, refs)
    return LookupOut(
        entity_type=entity_type,
        source=source,
        resolved=resolved,
        # Order preserved from the request so a caller can line results up
        # against what it sent.
        unresolved=[r for r in refs if r not in resolved],
    )


@router.get("/{entity_type}/{internal_id}/aliases", response_model=AliasesOut)
async def aliases(
    entity_type: str,
    internal_id: int,
    session: AsyncSession = Depends(get_session),
    _: ApiKey = Depends(require_api_key),
):
    """Every provider id known for one gateway row.

    The reverse direction, for a consumer checking its own mapping against
    ours, or reconciling after adding a second upstream source.
    """
    _validate_entity_type(entity_type)

    rows = await IdMapper(session).aliases(entity_type, internal_id)
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No {entity_type} with id {internal_id}, or no mappings for it",
        )

    return AliasesOut(
        entity_type=entity_type,
        internal_id=internal_id,
        aliases=[
            AliasOut(
                source=row.source,
                external_id=row.external_id,
                verified=row.verified,
            )
            for row in rows
        ],
    )
