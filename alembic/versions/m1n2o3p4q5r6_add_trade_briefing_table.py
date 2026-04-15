"""add trade_briefing table

Revision ID: m1n2o3p4q5r6
Revises: l1m2n3o4p5q6
Create Date: 2026-04-15 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'm1n2o3p4q5r6'
down_revision: Union[str, Sequence[str], None] = 'l1m2n3o4p5q6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('trade_briefing',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session', sa.String(length=20), nullable=False,
                  comment='morning/evening'),
        sa.Column('brief_date', sa.Date(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session', 'brief_date',
                            name='uk_session_date'),
    )


def downgrade() -> None:
    op.drop_table('trade_briefing')
