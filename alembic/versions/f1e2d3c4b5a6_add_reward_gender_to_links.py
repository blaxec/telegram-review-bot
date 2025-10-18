"""add reward gender to links

Revision ID: f1e2d3c4b5a6
Revises: e1d2c3b4a5f6
Create Date: 2025-10-10 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f1e2d3c4b5a6'
down_revision: Union[str, None] = 'e1d2c3b4a5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# --- ИЗМЕНЕНИЕ: Определяем тип вручную ---
GENDER_ENUM = sa.Enum('any', 'male', 'female', name='gender_enum')

def upgrade() -> None:
    # --- ИЗМЕНЕНИЕ: Создаем тип отдельной SQL командой ---
    op.execute("CREATE TYPE gender_enum AS ENUM ('any', 'male', 'female')")
    
    op.add_column('links', sa.Column('reward_amount', sa.Float(), server_default=sa.text("'0.0'"), nullable=False))
    op.add_column('links', sa.Column('gender_requirement', GENDER_ENUM, server_default=sa.text("'any'"), nullable=False))

def downgrade() -> None:
    op.drop_column('links', 'gender_requirement')
    op.drop_column('links', 'reward_amount')

    # --- ИЗМЕНЕНИЕ: Удаляем тип отдельной SQL командой ---
    op.execute("DROP TYPE gender_enum")