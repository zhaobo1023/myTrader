"""add candidate pool tables

Revision ID: i1j2k3l4m5n6
Revises: h1i2j3k4l5m6
Create Date: 2026-04-14 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'i1j2k3l4m5n6'
down_revision: Union[str, Sequence[str], None] = 'h1i2j3k4l5m6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'candidate_pool_stocks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('stock_code', sa.String(12), nullable=False),
        sa.Column('stock_name', sa.String(20), nullable=False, server_default=''),
        sa.Column('source_type',
                  sa.Enum('industry', 'strategy', 'manual', name='candidate_source_type'),
                  nullable=False),
        sa.Column('source_detail', sa.String(100), nullable=True),
        sa.Column('entry_snapshot', sa.Text(), nullable=True),
        sa.Column('add_date', sa.Date(), nullable=False),
        sa.Column('status',
                  sa.Enum('watching', 'focused', 'excluded', name='candidate_status'),
                  nullable=False, server_default='watching'),
        sa.Column('memo', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stock_code', name='uq_candidate_stock_code'),
    )
    op.create_index('ix_candidate_pool_stocks_source', 'candidate_pool_stocks', ['source_type', 'add_date'])
    op.create_index('ix_candidate_pool_stocks_status', 'candidate_pool_stocks', ['status'])

    op.create_table(
        'candidate_monitor_daily',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('stock_code', sa.String(12), nullable=False),
        sa.Column('trade_date', sa.Date(), nullable=False),
        sa.Column('close', sa.Double(), nullable=True),
        sa.Column('rps_250', sa.Double(), nullable=True),
        sa.Column('rps_120', sa.Double(), nullable=True),
        sa.Column('rps_20', sa.Double(), nullable=True),
        sa.Column('rps_slope', sa.Double(), nullable=True),
        sa.Column('ma20', sa.Double(), nullable=True),
        sa.Column('ma60', sa.Double(), nullable=True),
        sa.Column('ma250', sa.Double(), nullable=True),
        sa.Column('volume_ratio', sa.Double(), nullable=True),
        sa.Column('rsi', sa.Double(), nullable=True),
        sa.Column('macd_dif', sa.Double(), nullable=True),
        sa.Column('macd_dea', sa.Double(), nullable=True),
        sa.Column('pct_since_add', sa.Double(), nullable=True),
        sa.Column('rps_change', sa.Double(), nullable=True),
        sa.Column('signals', sa.Text(), nullable=True),
        sa.Column('alert_level',
                  sa.Enum('red', 'yellow', 'green', 'info', name='candidate_alert_level'),
                  nullable=False, server_default='info'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stock_code', 'trade_date', name='uq_candidate_monitor_code_date'),
    )
    op.create_index('ix_candidate_monitor_daily_date', 'candidate_monitor_daily', ['trade_date'])
    op.create_index('ix_candidate_monitor_daily_alert', 'candidate_monitor_daily', ['trade_date', 'alert_level'])


def downgrade() -> None:
    op.drop_index('ix_candidate_monitor_daily_alert', 'candidate_monitor_daily')
    op.drop_index('ix_candidate_monitor_daily_date', 'candidate_monitor_daily')
    op.drop_table('candidate_monitor_daily')
    op.drop_index('ix_candidate_pool_stocks_status', 'candidate_pool_stocks')
    op.drop_index('ix_candidate_pool_stocks_source', 'candidate_pool_stocks')
    op.drop_table('candidate_pool_stocks')
    op.execute("DROP TYPE IF EXISTS candidate_source_type")
    op.execute("DROP TYPE IF EXISTS candidate_status")
    op.execute("DROP TYPE IF EXISTS candidate_alert_level")
