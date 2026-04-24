# -*- coding: utf-8 -*-
"""Add candidate_pool_memos table

Revision ID: a1b2c3d4e5f6
Revises: z1a2b3c4d5e6
Create Date: 2026-04-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'ef2b16c38708'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'candidate_pool_memos',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('candidate_stock_id', sa.Integer(), nullable=False),
        sa.Column('content', sa.String(1000), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_candidate_pool_memos_stock', 'candidate_pool_memos', ['candidate_stock_id'])


def downgrade() -> None:
    op.drop_index('ix_candidate_pool_memos_stock', table_name='candidate_pool_memos')
    op.drop_table('candidate_pool_memos')
