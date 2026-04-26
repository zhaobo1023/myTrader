# -*- coding: utf-8 -*-
"""Add wechat_feeds table

Revision ID: b1c2d3e4f5g6
Revises: a1b2c3d4e5f6
Create Date: 2026-04-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b1c2d3e4f5g6'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'wechat_feeds',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('feed_id', sa.String(255), nullable=False, unique=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('url', sa.String(1024), nullable=True),
        sa.Column('is_active', sa.Integer(), default=1, nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('feed_id', name='uq_feed_id'),
    )
    op.create_index('ix_wechat_feeds_feed_id', 'wechat_feeds', ['feed_id'])
    op.create_index('ix_wechat_feeds_is_active', 'wechat_feeds', ['is_active'])


def downgrade() -> None:
    op.drop_index('ix_wechat_feeds_is_active', table_name='wechat_feeds')
    op.drop_index('ix_wechat_feeds_feed_id', table_name='wechat_feeds')
    op.drop_table('wechat_feeds')
