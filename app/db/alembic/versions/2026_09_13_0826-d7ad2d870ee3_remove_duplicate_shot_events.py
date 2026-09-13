"""remove duplicate shot events

A data migration, not a schema one - autogenerate has nothing to detect
here because the table shape is unchanged.

Upstream occasionally emits one shot twice under two different ids. The
sync path deduplicated on the provider's id, which cannot catch that, so
the copies were stored. On one fixture every goal was doubled and the
score derived from shot data came out 4-6 for a match that finished 2-3.

Deleting on the full natural key - player, minute, result, xG and
coordinates. Shots identical to four decimals of xG *and* to the same
coordinates are one event recorded twice. Anything looser would delete
real rebounds: two blocked shots by the same player in the same minute
happens, and 13 of the 14 fixtures that look duplicated on
(player, minute, result) alone are exactly that.

Keeps the lowest external_ref of each group, arbitrary but deterministic,
so re-running cannot pick a different survivor.

Revision ID: d7ad2d870ee3
Revises: 2352f037497e
Create Date: 2026-09-13 08:26:47.528049

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7ad2d870ee3"
down_revision: Union[str, Sequence[str], None] = "2352f037497e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM shot_events
         WHERE id IN (
           SELECT id FROM (
             SELECT id,
                    ROW_NUMBER() OVER (
                      PARTITION BY fixture_id, team_id, player_name, minute,
                                   result, xg, location_x, location_y
                      ORDER BY external_ref
                    ) AS rn
               FROM shot_events
           ) ranked
          WHERE ranked.rn > 1
         )
        """
    )


def downgrade() -> None:
    """Deliberately empty.

    The deleted rows were duplicates of rows that remain, so there is
    nothing to restore that is not already present. Re-syncing the affected
    fixtures would rebuild the table from upstream anyway - this schema is
    a cache.
    """
