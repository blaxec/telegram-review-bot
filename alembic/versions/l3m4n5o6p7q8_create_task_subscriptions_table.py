# telegram-review-bot-main/alembic/versions/l3m4n5o6p7q8_create_task_subscriptions_table.py

"""create task_subscriptions table
Revision ID: l3m4n5o6p7q8
Revises: m9n0o1p2q3r4
Create Date: 2025-10-10 13:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'l3m4n5o6p7q8'
down_revision: Union[str, None] = 'm9n0o1p2q3r4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    # --- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: Создаем таблицу с временным типом (String) ---
    op.create_table('task_subscriptions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('gender', sa.String(), nullable=False), # Временный тип
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'platform', 'gender')
    )

    # --- А теперь меняем тип колонки на правильный с помощью SQL ---
    # Тип 'gender_enum' к этому моменту уже должен быть создан предыдущей миграцией.
    op.execute("""
        ALTER TABLE task_subscriptions
        ALTER COLUMN gender TYPE gender_enum
        USING gender::gender_enum;
    """)

def downgrade() -> None:
    op.drop_table('task_subscriptions')