# -*- coding: utf-8 -*-
"""Add user_id to candidate_pool_stocks

Revision ID: a1b2c3d4e5f6
Revises: z1a2b3c4d5e6
Create Date: 2026-04-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'z1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('candidate_pool_stocks', sa.Column('user_id', sa.Integer(), nullable=False, server_default='0'))
    op.drop_constraint('uq_candidate_stock_code', 'candidate_pool_stocks', type_='unique')
    op.create_unique_constraint('uq_candidate_user_stock', 'candidate_pool_stocks', ['user_id', 'stock_code'])
    op.drop_index('ix_candidate_pool_stocks_source', table_name='candidate_pool_stocks')
    op.drop_index('ix_candidate_pool_stocks_status', table_name='candidate_pool_stocks')
    op.create_index('ix_candidate_pool_stocks_user', 'candidate_pool_stocks', ['user_id'])
    op.create_index('ix_candidate_pool_stocks_source', 'candidate_pool_stocks', ['user_id', 'source_type', 'add_date'])
    op.create_index('ix_candidate_pool_stocks_status', 'candidate_pool_stocks', ['user_id', 'status'])


def downgrade() -> None:
    op.drop_index('ix_candidate_pool_stocks_status', table_name='candidate_pool_stocks')
    op.drop_index('ix_candidate_pool_stocks_source', table_name='candidate_pool_stocks')
    op.drop_index('ix_candidate_pool_stocks_user', table_name='candidate_pool_stocks')
    op.drop_constraint('uq_candidate_user_stock', 'candidate_pool_stocks', type_='unique')
    op.create_unique_constraint('uq_candidate_stock_code', 'candidate_pool_stocks', ['stock_code'])
    op.drop_column('candidate_pool_stocks', 'user_id')
