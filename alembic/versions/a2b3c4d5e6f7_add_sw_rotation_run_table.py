"""add sw rotation run table

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-04-12 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a2b3c4d5e6f7'
down_revision: Union[str, Sequence[str], None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'trade_sw_rotation_run',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('run_date', sa.Date(), nullable=False, comment='Friday date of the week'),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending',
                  comment='pending/running/done/failed'),
        sa.Column('triggered_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('industry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('hot_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('rising_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('startup_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('retreat_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('scores_json', sa.Text(16777215), nullable=True,
                  comment='JSON list of industry scores'),
        sa.Column('error_msg', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_date', name='uq_sw_run_date'),
    )


def downgrade() -> None:
    op.drop_table('trade_sw_rotation_run')
