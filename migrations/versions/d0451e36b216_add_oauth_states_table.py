"""add oauth_states table

Revision ID: d0451e36b216
Revises: eef93debeb8c
Create Date: 2026-09-22 23:27:45.097868

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd0451e36b216'
down_revision: Union[str, Sequence[str], None] = 'eef93debeb8c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('oauth_states',
    sa.Column('state', sa.String(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('state')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('oauth_states')
