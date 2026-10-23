"""add profile fields to users

Revision ID: c1d9f2a7b4e3
Revises: aa03f4502d59
Create Date: 2026-10-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d9f2a7b4e3'
down_revision: Union[str, Sequence[str], None] = 'aa03f4502d59'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('username', sa.String(), nullable=True))
    op.add_column('users', sa.Column('f_name', sa.String(), nullable=True))
    op.add_column('users', sa.Column('l_name', sa.String(), nullable=True))
    op.add_column('users', sa.Column('profile_photo', sa.String(), nullable=True))
    op.add_column('users', sa.Column('lifetime_steps', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('postcards_sum', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('member_since', sa.Date(), nullable=False, server_default=sa.func.current_date()))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'member_since')
    op.drop_column('users', 'postcards_sum')
    op.drop_column('users', 'lifetime_steps')
    op.drop_column('users', 'profile_photo')
    op.drop_column('users', 'l_name')
    op.drop_column('users', 'f_name')
    op.drop_column('users', 'username')
