"""drop api_keys.revoked_at

Revision ID: 882ea5b5f80c
Revises: 84dfb5b4f329
Create Date: 2026-09-24 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '882ea5b5f80c'
down_revision: Union[str, Sequence[str], None] = '84dfb5b4f329'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Revocation deletes the row instead of flagging it - see
    # ApiKeyRecord's docstring - so this column never gets read or
    # written to anymore.
    op.drop_column('api_keys', 'revoked_at')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        'api_keys',
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    )
