"""add trade_limit_stock_detail table

Revision ID: p1q2r3s4t5u6
Revises: o1p2q3r4s5t6
Create Date: 2026-04-15 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'p1q2r3s4t5u6'
down_revision: Union[str, Sequence[str], None] = 'o1p2q3r4s5t6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('trade_limit_stock_detail',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('trade_date', sa.Date(), nullable=False),
        sa.Column('direction', sa.String(length=10), nullable=False,
                  comment='up or down'),
        sa.Column('stock_code', sa.String(length=20), nullable=False),
        sa.Column('stock_name', sa.String(length=50), nullable=False),
        sa.Column('industry', sa.String(length=50), nullable=True),
        sa.Column('change_pct', sa.Double(), nullable=True),
        sa.Column('amount', sa.Double(), nullable=True,
                  comment='turnover in yuan'),
        sa.Column('consecutive', sa.Integer(), nullable=True,
                  server_default=sa.text('1'),
                  comment='consecutive limit days'),
        sa.Column('first_limit_time', sa.String(length=10), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('trade_date', 'direction', 'stock_code',
                            name='uk_date_dir_code'),
        sa.Index('idx_limit_date', 'trade_date'),
    )


def downgrade() -> None:
    op.drop_table('trade_limit_stock_detail')
