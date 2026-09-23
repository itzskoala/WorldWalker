"""add email hashed_password is_active to users

Revision ID: eef93debeb8c
Revises: 92ff7381ebca
Create Date: 2026-09-22 21:33:03.995925

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eef93debeb8c'
down_revision: Union[str, Sequence[str], None] = '92ff7381ebca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('email', sa.String(), nullable=True))
    op.add_column('users', sa.Column('hashed_password', sa.String(), nullable=True))
    op.add_column('users', sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False))
    op.create_unique_constraint('uq_users_email', 'users', ['email'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_users_email', 'users', type_='unique')
    op.drop_column('users', 'is_active')
    op.drop_column('users', 'hashed_password')
    op.drop_column('users', 'email')
