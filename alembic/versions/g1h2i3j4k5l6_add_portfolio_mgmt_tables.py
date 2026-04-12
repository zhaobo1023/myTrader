"""add portfolio mgmt tables

Revision ID: g1h2i3j4k5l6
Revises: a2b3c4d5e6f7
Create Date: 2026-04-13 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'g1h2i3j4k5l6'
down_revision: Union[str, Sequence[str], None] = 'a2b3c4d5e6f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'portfolio_stock',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False, server_default='0',
                  comment='Reserved for multi-tenant, single user fixed 0'),
        sa.Column('stock_code', sa.String(20), nullable=False),
        sa.Column('stock_name', sa.String(50), nullable=False, server_default=''),
        sa.Column('industry', sa.String(50), nullable=False, server_default=''),
        sa.Column('tier', sa.String(20), nullable=False, server_default='',
                  comment='Tier: Far Ahead | Leading'),
        sa.Column('status', sa.String(10), nullable=False, server_default='hold',
                  comment='hold | watch'),
        sa.Column('position_pct', sa.DECIMAL(5, 2), nullable=False, server_default='0'),
        sa.Column('profit_26', sa.DECIMAL(12, 2), nullable=True),
        sa.Column('profit_27', sa.DECIMAL(12, 2), nullable=True),
        sa.Column('pe_26', sa.DECIMAL(6, 2), nullable=True),
        sa.Column('pe_27', sa.DECIMAL(6, 2), nullable=True),
        sa.Column('net_cash_26', sa.DECIMAL(12, 2), nullable=False, server_default='0'),
        sa.Column('net_cash_27', sa.DECIMAL(12, 2), nullable=False, server_default='0'),
        sa.Column('cash_adj_coef', sa.DECIMAL(4, 2), nullable=False, server_default='0.50'),
        sa.Column('equity_adj', sa.DECIMAL(12, 2), nullable=False, server_default='0'),
        sa.Column('asset_growth_26', sa.DECIMAL(12, 2), nullable=False, server_default='0'),
        sa.Column('asset_growth_27', sa.DECIMAL(12, 2), nullable=False, server_default='0'),
        sa.Column('payout_ratio', sa.DECIMAL(5, 4), nullable=False, server_default='0',
                  comment='Dividend + buyback payout ratio'),
        sa.Column('research_depth', sa.Integer(), nullable=False, server_default='80'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'stock_code', name='uq_user_code'),
    )

    op.create_table(
        'portfolio_optimizer_run',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('run_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('input_snapshot', sa.Text(16777215), nullable=False,
                  comment='JSON snapshot of all stock assumptions at run time'),
        sa.Column('result_json', sa.Text(16777215), nullable=False,
                  comment='JSON: {code: pct}'),
        sa.Column('metrics_json', sa.Text(16777215), nullable=False,
                  comment='JSON: portfolio metrics'),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('portfolio_optimizer_run')
    op.drop_table('portfolio_stock')
