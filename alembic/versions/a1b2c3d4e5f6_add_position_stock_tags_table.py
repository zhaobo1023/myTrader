# -*- coding: utf-8 -*-
"""Add position_stock_tags table

Revision ID: a1b2c3d4e5f6
Revises: z1a2b3c4d5e6
Create Date: 2026-04-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'z1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'position_stock_tags',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('position_id', sa.Integer(), nullable=False),
        sa.Column('tag_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('position_id', 'tag_id', name='uq_position_stock_tag'),
    )
    op.create_index('ix_position_stock_tags_position', 'position_stock_tags', ['position_id'])
    op.create_index('ix_position_stock_tags_tag', 'position_stock_tags', ['tag_id'])


def downgrade() -> None:
    op.drop_index('ix_position_stock_tags_tag', table_name='position_stock_tags')
    op.drop_index('ix_position_stock_tags_position', table_name='position_stock_tags')
    op.drop_table('position_stock_tags')
