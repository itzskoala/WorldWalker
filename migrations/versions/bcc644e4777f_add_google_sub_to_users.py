"""add google_sub to users

Revision ID: bcc644e4777f
Revises: 745142a3bb1c
Create Date: 2026-09-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bcc644e4777f'
down_revision: Union[str, Sequence[str], None] = '745142a3bb1c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('google_sub', sa.String(), nullable=True))
    op.create_unique_constraint('uq_users_google_sub', 'users', ['google_sub'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_users_google_sub', 'users', type_='unique')
    op.drop_column('users', 'google_sub')
