"""add stock_concept_map table

Revision ID: l1m2n3o4p5q6
Revises: k1l2m3n4o5p6
Create Date: 2026-04-15 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'l1m2n3o4p5q6'
down_revision: Union[str, Sequence[str], None] = 'k1l2m3n4o5p6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'stock_concept_map',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('stock_code', sa.String(12), nullable=False, comment='股票代码 (带后缀, e.g. 600519.SH)'),
        sa.Column('stock_name', sa.String(50), nullable=False, comment='股票名称'),
        sa.Column('concept_name', sa.String(100), nullable=False, comment='东财概念板块名称'),
        sa.Column('updated_at', sa.DateTime(), nullable=False, comment='最近同步时间'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stock_code', 'concept_name', name='uk_stock_concept'),
    )
    op.create_index('ix_concept_name', 'stock_concept_map', ['concept_name'])
    op.create_index('ix_stock_concept_map_stock_code', 'stock_concept_map', ['stock_code'])


def downgrade() -> None:
    op.drop_index('ix_stock_concept_map_stock_code', table_name='stock_concept_map')
    op.drop_index('ix_concept_name', table_name='stock_concept_map')
    op.drop_table('stock_concept_map')
