from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlmodel import Field, SQLModel

from app.utils.datetime_utils import utcnow

# Gateway ids start here so they can never be mistaken for, or collide
# with, an upstream provider's id.
#
# This is not theoretical: football-data.org numbers teams from 1 (Köln is
# 1, Dortmund is 4), and its fixture ids sit around 560,000. api-sports
# fixture ids are around 1.5 million. A consumer migrating between sources
# holds both kinds in one column for a while, and with low ids there is no
# way to tell them apart - or to stop one overwriting the other.
#
# Starting above every range in use makes a gateway id recognisable on
# sight and keeps the two namespaces disjoint by construction.
ID_SEQUENCE_START = 10_000_000


class EntityType:
    """Entities that carry a gateway id. Plain strings rather than an enum
    so a new entity type does not need a database migration."""

    LEAGUE = "league"
    TEAM = "team"
    FIXTURE = "fixture"


class ExternalId(SQLModel, table=True):
    """Maps an upstream provider's identifier to this gateway's own id.

    The gateway's promise is that you can swap or add upstream sources
    without consumers changing anything. That is only true if consumers
    build against ids this gateway controls. While provider ids were used
    as primary keys, the promise could not hold: the moment a second
    connector is registered, two providers disagree about which number
    means Arsenal, and `SyncService._first_success` would write rows under
    whichever one happened to answer first.

    This table is where that disagreement gets resolved. One club has one
    gateway id and as many rows here as there are sources that know it.

    It also gives consumers a migration path. Someone already keyed to
    another provider can ask "which of your teams is this provider's 57?"
    and adopt gateway ids gradually, instead of re-keying their history in
    one step.

    Note that matching a club across providers is not automatic - names
    differ ("Brighton" vs "Brighton & Hove Albion FC"), so rows sourced
    from name matching need review before they are trusted. See
    `verified`.
    """

    __tablename__: str = "external_ids"
    __table_args__ = (
        # One provider id means one thing. Without this, a re-sync that
        # resolved a name differently could quietly attach a second
        # gateway id to the same upstream club.
        sa.UniqueConstraint(
            "entity_type", "source", "external_id", name="uq_external_ids_source_ref"
        ),
        # The common read: "given this provider's id, what is ours?"
        sa.Index("ix_external_ids_lookup", "entity_type", "source", "external_id"),
        # The reverse read, for serving a row's known aliases.
        sa.Index("ix_external_ids_internal", "entity_type", "internal_id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)

    entity_type: str = Field(max_length=20, nullable=False)
    source: str = Field(max_length=50, nullable=False)

    # Text rather than int: provider ids are usually numeric, but not
    # always - football-data.org identifies competitions by code ("PL") in
    # its URLs, and a future connector may use a slug or a UUID.
    external_id: str = Field(max_length=100, nullable=False)

    internal_id: int = Field(nullable=False)

    # False for anything inferred rather than told to us - a mapping
    # derived from matching club names, say. Unverified mappings are a
    # suggestion, not a fact, and callers should be able to tell the
    # difference before relying on one.
    verified: bool = Field(default=True, nullable=False)

    created_at: Optional[datetime] = Field(
        default_factory=utcnow, sa_column=sa.Column(sa.DateTime(timezone=True))
    )
