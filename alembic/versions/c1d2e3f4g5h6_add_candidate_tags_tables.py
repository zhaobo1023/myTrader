# -*- coding: utf-8 -*-
"""Add candidate_tags and candidate_stock_tags tables

Revision ID: c1d2e3f4g5h6
Revises: a1b2c3d4e5f6
Create Date: 2026-04-24
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c1d2e3f4g5h6'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'candidate_tags',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(30), nullable=False),
        sa.Column('color', sa.String(20), nullable=False, server_default='#5e6ad2'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'name', name='uq_candidate_tag_user_name'),
    )
    op.create_index('ix_candidate_tags_user', 'candidate_tags', ['user_id'])

    op.create_table(
        'candidate_stock_tags',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('stock_id', sa.Integer(), nullable=False),
        sa.Column('tag_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stock_id', 'tag_id', name='uq_candidate_stock_tag'),
    )
    op.create_index('ix_candidate_stock_tags_stock', 'candidate_stock_tags', ['stock_id'])
    op.create_index('ix_candidate_stock_tags_tag', 'candidate_stock_tags', ['tag_id'])


def downgrade() -> None:
    op.drop_table('candidate_stock_tags')
    op.drop_table('candidate_tags')
