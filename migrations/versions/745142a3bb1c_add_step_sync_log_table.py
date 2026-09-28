"""add step_sync_log table

Revision ID: 745142a3bb1c
Revises: 83a2b54e395c
Create Date: 2026-09-23 19:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '745142a3bb1c'
down_revision: Union[str, Sequence[str], None] = '83a2b54e395c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('step_sync_log',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('trip_id', sa.UUID(), nullable=False),
    sa.Column('steps', sa.Integer(), nullable=False),
    sa.Column('distance_walked_miles', sa.Float(), nullable=False),
    sa.Column('distance_remaining_miles', sa.Float(), nullable=False),
    sa.Column('percent_complete', sa.Float(), nullable=False),
    sa.Column('synced_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['trip_id'], ['active_trips.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_step_sync_log_user_id'), 'step_sync_log', ['user_id'], unique=False)
    op.create_index(op.f('ix_step_sync_log_trip_id'), 'step_sync_log', ['trip_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_step_sync_log_trip_id'), table_name='step_sync_log')
    op.drop_index(op.f('ix_step_sync_log_user_id'), table_name='step_sync_log')
    op.drop_table('step_sync_log')
