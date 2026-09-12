from typing import Dict, List, Optional

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.db.models import ExternalId


class IdMapper:
    """Translates an upstream provider's identifiers into gateway ids.

    Every sync method needs the same question answered - "I have
    football-data.org's team 57, which row is that?" - so it lives here
    rather than being repeated, and so it can be tested without standing up
    a connector.

    Before this existed, provider ids *were* the primary keys and the
    answer was "the same number". That could not survive a second
    connector: two providers number Arsenal differently, and whichever
    answered first would own the row.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def resolve(
        self,
        entity_type: str,
        source: str,
        external_ref: str,
        verified_only: bool = False,
    ) -> Optional[int]:
        """Gateway id for one provider ref, or None if never seen.

        `verified_only` excludes mappings that were guessed from names and
        not yet reviewed. The sync path sets it: writing a fixture against
        a guessed team mapping produces data that is silently wrong, and
        skipping is the behaviour it already has for unknown refs. Lookups
        leave it off, because there a human is reading the answer and the
        `verified` flag travels with it.
        """
        query = select(ExternalId).where(
            ExternalId.entity_type == entity_type,
            ExternalId.source == source,
            ExternalId.external_id == str(external_ref),
        )
        if verified_only:
            query = query.where(ExternalId.verified == True)  # noqa: E712
        row = (await self.session.exec(query)).first()
        return row.internal_id if row else None

    async def resolve_many(
        self,
        entity_type: str,
        source: str,
        external_refs: List[str],
        verified_only: bool = False,
    ) -> Dict[str, int]:
        """Bulk `resolve`, keyed by ref.

        One query for a whole matchday rather than one per fixture - the
        sync methods resolve tens to hundreds of refs at a time, and the
        per-row version turns a single sync into hundreds of round trips.
        """
        refs = [str(r) for r in external_refs]
        if not refs:
            return {}

        query = select(ExternalId).where(
            ExternalId.entity_type == entity_type,
            ExternalId.source == source,
            ExternalId.external_id.in_(refs),
        )
        if verified_only:
            query = query.where(ExternalId.verified == True)  # noqa: E712
        rows = (await self.session.exec(query)).all()
        return {row.external_id: row.internal_id for row in rows}

    async def link(
        self,
        entity_type: str,
        source: str,
        external_ref: str,
        internal_id: int,
        verified: bool = True,
    ) -> ExternalId:
        """Record that a provider's ref means this gateway row.

        Idempotent: syncs run repeatedly over the same fixtures, so calling
        this again for a known ref returns the existing mapping rather than
        racing the unique constraint.

        A ref is never silently repointed at a different row. If the same
        provider id already maps elsewhere, that is a real conflict - two
        gateway rows claiming one upstream entity - and it should surface
        rather than be papered over by an update.
        """
        existing = (
            await self.session.exec(
                select(ExternalId).where(
                    ExternalId.entity_type == entity_type,
                    ExternalId.source == source,
                    ExternalId.external_id == str(external_ref),
                )
            )
        ).first()

        if existing:
            if existing.internal_id != internal_id:
                raise ValueError(
                    f"{entity_type} {source}:{external_ref} is already mapped to "
                    f"{existing.internal_id}, refusing to repoint it at {internal_id}"
                )
            # Promote a guess to a fact if this caller knows better, but
            # never demote something already confirmed.
            if verified and not existing.verified:
                existing.verified = True
                self.session.add(existing)
            return existing

        mapping = ExternalId(
            entity_type=entity_type,
            source=source,
            external_id=str(external_ref),
            internal_id=internal_id,
            verified=verified,
        )
        self.session.add(mapping)
        return mapping

    async def aliases(self, entity_type: str, internal_id: int) -> List[ExternalId]:
        """Every provider ref known for one gateway row.

        The reverse direction, for serving a row's identifiers to consumers
        migrating from another provider.
        """
        return list(
            (
                await self.session.exec(
                    select(ExternalId).where(
                        ExternalId.entity_type == entity_type,
                        ExternalId.internal_id == internal_id,
                    )
                )
            ).all()
        )
