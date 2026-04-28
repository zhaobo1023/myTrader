# -*- coding: utf-8 -*-
"""Add source column to stock_concept_map

Revision ID: z3a4b5c6d7e8
Revises: z2a3b4c5d6e7
Create Date: 2026-04-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'z3a4b5c6d7e8'
down_revision: Union[str, Sequence[str], None] = 'z2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'stock_concept_map',
        sa.Column('source', sa.String(20), nullable=False, server_default='em',
                  comment='em/tushare/ths'),
    )
    op.create_index('ix_source', 'stock_concept_map', ['source'])


def downgrade() -> None:
    op.drop_index('ix_source', table_name='stock_concept_map')
    op.drop_column('stock_concept_map', 'source')
