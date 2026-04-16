"""add structured_data column to trade_briefing

Revision ID: q1r2s3t4u5v6
Revises: p1q2r3s4t5u6
Create Date: 2026-04-15 22:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'q1r2s3t4u5v6'
down_revision: Union[str, Sequence[str], None] = 'p1q2r3s4t5u6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('trade_briefing',
        sa.Column('structured_data', sa.JSON(), nullable=True,
                  comment='raw data context fed to LLM'))


def downgrade() -> None:
    op.drop_column('trade_briefing', 'structured_data')
