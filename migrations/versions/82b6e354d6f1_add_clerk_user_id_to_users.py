"""add clerk_user_id to users

Revision ID: 82b6e354d6f1
Revises: 871536f8b346
Create Date: 2026-10-06 17:15:30.420397

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '82b6e354d6f1'
down_revision: Union[str, Sequence[str], None] = '871536f8b346'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('clerk_user_id', sa.String(), nullable=True))
    op.create_unique_constraint('uq_users_clerk_user_id', 'users', ['clerk_user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_users_clerk_user_id', 'users', type_='unique')
    op.drop_column('users', 'clerk_user_id')
