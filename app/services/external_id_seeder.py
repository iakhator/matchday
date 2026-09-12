"""Propose, review, approve - seeding the id map from another provider.

Sources that give us their own identifiers need none of this. This is for
the ones that only give names, where the mapping has to be guessed and
therefore has to be checked.

The flow is deliberately three steps with a file in the middle:

    propose   match names, write every result as verified=False
    review    a human edits the emitted file
    approve   import it, flipping approved rows to verified=True

The file matters. It makes the review a reviewable artefact - committable,
diffable, and attributable - rather than a decision someone made once in a
terminal. When a mapping later turns out to be wrong, the question "who
approved this and what did it look like at the time?" has an answer.

Nothing here ever marks a mapping verified on its own.
"""

from typing import Dict, List, Sequence

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.logger import logger
from app.db.models import EntityType, ExternalId, Team
from app.services.id_mapper import IdMapper
from app.services.name_matcher import Confidence, Proposal, propose


class ExternalIdSeeder:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.ids = IdMapper(session)

    async def propose_team_mappings(
        self, source: str, entries: Sequence[Dict[str, str]]
    ) -> List[Proposal]:
        """Match `entries` against known teams and record the confident ones
        as unverified mappings.

        Only EXACT and STRONG are written. WEAK, AMBIGUOUS and NONE are
        returned for review but deliberately not persisted - a weak guess
        in the table is worse than an absent one, because absent is honest
        about not knowing.
        """
        teams = (await self.session.exec(select(Team))).all()
        candidates = [{"id": t.id, "name": t.name} for t in teams]
        # short_name is a second chance at a match: providers differ on
        # whether they use "Brighton" or the full registered name, and
        # either side may be the short one.
        for team in teams:
            if team.short_name and team.short_name != team.name:
                candidates.append({"id": team.id, "name": team.short_name})

        proposals = propose(entries, candidates)

        written = 0
        for proposal in proposals:
            if proposal.confidence not in (Confidence.EXACT, Confidence.STRONG):
                continue
            if proposal.internal_id is None:
                continue
            existing = await self.ids.resolve(
                EntityType.TEAM, source, proposal.external_id
            )
            if existing is not None:
                # Already mapped - never silently repoint. If the proposal
                # disagrees with what is recorded, the reviewer should see
                # that, not have it overwritten underneath them.
                continue
            await self.ids.link(
                EntityType.TEAM,
                source,
                proposal.external_id,
                proposal.internal_id,
                verified=False,
            )
            written += 1

        await self.session.commit()
        logger.info(
            f"Proposed {written} unverified team mappings for source '{source}' "
            f"from {len(entries)} entries"
        )
        return proposals

    async def approve(
        self, source: str, external_ids: Sequence[str], entity_type: str = None
    ) -> int:
        """Mark reviewed mappings as verified.

        Takes the ids a human signed off on, not "everything proposed
        earlier" - approving by batch would let a row added between propose
        and approve slip through unlooked-at.
        """
        entity_type = entity_type or EntityType.TEAM
        refs = [str(r) for r in external_ids]
        if not refs:
            return 0

        rows = (
            await self.session.exec(
                select(ExternalId).where(
                    ExternalId.entity_type == entity_type,
                    ExternalId.source == source,
                    ExternalId.external_id.in_(refs),
                )
            )
        ).all()

        approved = 0
        for row in rows:
            if not row.verified:
                row.verified = True
                self.session.add(row)
                approved += 1

        await self.session.commit()
        logger.info(f"Approved {approved} mappings for source '{source}'")
        return approved

    async def pending(self, source: str = None) -> List[ExternalId]:
        """Mappings still awaiting review."""
        query = select(ExternalId).where(ExternalId.verified == False)  # noqa: E712
        if source:
            query = query.where(ExternalId.source == source)
        return list((await self.session.exec(query)).all())


def to_review_document(source: str, proposals: Sequence[Proposal]) -> dict:
    """Shape the proposals for a human to read and edit.

    Grouped by what the reviewer has to *do*, not by confidence as a label:
    confirm a suggestion, choose between alternatives, or find a match by
    hand. Sorted so the same input produces the same file and a re-run
    diffs cleanly against the last one.
    """
    confirm, choose, manual = [], [], []

    for proposal in sorted(proposals, key=lambda p: p.external_name.lower()):
        row = {
            "external_id": proposal.external_id,
            "external_name": proposal.external_name,
            "matched_id": proposal.internal_id,
            "matched_name": proposal.internal_name,
            "confidence": proposal.confidence,
            "approved": False,
        }
        if proposal.confidence in (Confidence.EXACT, Confidence.STRONG):
            confirm.append(row)
        elif proposal.confidence == Confidence.AMBIGUOUS:
            row["alternatives"] = proposal.alternatives
            choose.append(row)
        else:
            manual.append(row)

    return {
        "source": source,
        "instructions": (
            "Set approved=true on every row you have checked, then import "
            "this file. Rows left false stay unverified and are ignored by "
            "the sync path. For 'needs_manual_match', fill in matched_id "
            "yourself before approving."
        ),
        "summary": {
            "confirm": len(confirm),
            "needs_choice": len(choose),
            "needs_manual_match": len(manual),
        },
        "confirm": confirm,
        "needs_choice": choose,
        "needs_manual_match": manual,
    }
