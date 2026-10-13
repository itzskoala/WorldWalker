"""add checkpoint reveal radius and lazy metadata pipeline

Revision ID: 5a2f8c1e4d93
Revises: f89b5d8d5882
Create Date: 2026-10-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a2f8c1e4d93'
down_revision: Union[str, Sequence[str], None] = 'f89b5d8d5882'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Randomized once per trip now (travel_logic/checkpoints.py's
    # generate_reveal_radius_m(), a uniform 50-100m draw) - every
    # pre-existing trip backfills to the range's midpoint rather than a
    # value that would change its already-revealed checkpoints' behavior
    # one way or the other.
    op.add_column(
        'active_trips', sa.Column('checkpoint_reveal_radius_m', sa.Float(), server_default='75', nullable=False)
    )
    # Was only ever read to gate GET /api/journey/{id}/events's live
    # loop and the frontend's "should I open that stream" check - both
    # now key off trip.status == "completed" instead, since checkpoint
    # rows are generated synchronously at trip creation (there's no more
    # background "still discovering checkpoints" window to signal the
    # end of).
    op.drop_column('active_trips', 'checkpoints_ready_at')

    # revealed_at: proximity-based map visibility, independent of and
    # earlier than hit_at (see TripCheckpoint's docstring). metadata_
    # requested_at: when a background job last claimed this checkpoint
    # for name/description resolution - lets a stuck "processing" row be
    # told apart from one actively being worked on.
    op.add_column('trip_checkpoints', sa.Column('revealed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('trip_checkpoints', sa.Column('metadata_requested_at', sa.DateTime(timezone=True), nullable=True))

    op.drop_constraint('ck_trip_checkpoints_description_status', 'trip_checkpoints', type_='check')
    op.alter_column('trip_checkpoints', 'description_status', new_column_name='metadata_status')
    op.create_check_constraint(
        'ck_trip_checkpoints_metadata_status', 'trip_checkpoints', "metadata_status IN ('pending', 'processing', 'ready')"
    )

    # Every checkpoint written before this migration had its name/
    # description resolved synchronously, before the row ever existed -
    # it was already showing on the map regardless of description_status
    # (the old frontend never gated checkpoint *visibility* on it, only
    # which marker color/animation to use). revealed_at backfills to
    # hit_at for an already-passed checkpoint, or now() otherwise, so no
    # pre-existing checkpoint silently disappears under the new
    # reveal-gated map rendering.
    op.execute("UPDATE trip_checkpoints SET revealed_at = COALESCE(hit_at, now())")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('ck_trip_checkpoints_metadata_status', 'trip_checkpoints', type_='check')
    op.alter_column('trip_checkpoints', 'metadata_status', new_column_name='description_status')
    op.create_check_constraint(
        'ck_trip_checkpoints_description_status', 'trip_checkpoints', "description_status IN ('pending', 'ready')"
    )
    op.drop_column('trip_checkpoints', 'metadata_requested_at')
    op.drop_column('trip_checkpoints', 'revealed_at')

    op.add_column('active_trips', sa.Column('checkpoints_ready_at', sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE active_trips SET checkpoints_ready_at = now()")
    op.drop_column('active_trips', 'checkpoint_reveal_radius_m')
