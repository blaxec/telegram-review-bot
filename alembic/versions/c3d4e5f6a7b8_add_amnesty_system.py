# file: alembic/versions/c3d4e5f6a7b8_add_amnesty_system.py

"""Merge: add amnesty system and attached photo to review

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2025-09-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands from add_amnesty_system ###
    op.create_table('unban_requests',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('reason', sa.String(), nullable=False),
    sa.Column('status', sa.Enum('pending', 'approved', 'rejected', 'payment_pending', name='unban_request_status_enum'), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('reviewed_by_admin_id', sa.BigInteger(), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_unban_requests_user_id'), 'unban_requests', ['user_id'], unique=False)
    op.add_column('users', sa.Column('unban_count', sa.Integer(), nullable=False, server_default=sa.text('0')))
    
    # ### commands from add_attached_photo_to_review ###
    op.add_column('reviews', sa.Column('attached_photo_file_id', sa.String(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands from add_attached_photo_to_review ###
    op.drop_column('reviews', 'attached_photo_file_id')

    # ### commands from add_amnesty_system ###
    op.drop_column('users', 'unban_count')
    op.drop_index(op.f('ix_unban_requests_user_id'), table_name='unban_requests')
    op.drop_table('unban_requests')
    # ### end Alembic commands ###