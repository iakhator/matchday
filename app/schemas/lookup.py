from typing import Dict, List

from pydantic import BaseModel


class LookupOut(BaseModel):
    """Answer to "which of your rows are these provider ids?"

    `unresolved` is returned explicitly rather than left as absent keys in
    `resolved`. A consumer migrating from another provider needs to know
    precisely which of its entities this gateway does not recognise - those
    are the ones needing a human to look at them, and silently dropping
    them is how a migration ends up with holes nobody notices.
    """

    entity_type: str
    source: str
    resolved: Dict[str, int]
    unresolved: List[str]


class AliasOut(BaseModel):
    """One provider's name for a gateway row."""

    source: str
    external_id: str
    # False when the mapping was inferred (e.g. by matching club names)
    # rather than established from the provider's own identifiers. Treat an
    # unverified alias as a suggestion.
    verified: bool


class AliasesOut(BaseModel):
    entity_type: str
    internal_id: int
    aliases: List[AliasOut]
