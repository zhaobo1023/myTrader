# -*- coding: utf-8 -*-
"""add watchlist scan notify tables

Revision ID: cc8095756cc6
Revises: a1b2c3d4e5f6
Create Date: 2026-04-06 10:19:27.143823

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'cc8095756cc6'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create user_notification_configs, user_scan_results, user_watchlist tables."""
    op.create_table('user_notification_configs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('webhook_url', sa.String(length=500), nullable=True),
    sa.Column('notify_on_red', sa.Boolean(), nullable=False),
    sa.Column('notify_on_yellow', sa.Boolean(), nullable=False),
    sa.Column('notify_on_green', sa.Boolean(), nullable=False),
    sa.Column('score_threshold', sa.Float(), nullable=True),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    op.create_table('user_scan_results',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('stock_code', sa.String(length=20), nullable=False),
    sa.Column('stock_name', sa.String(length=50), nullable=False),
    sa.Column('scan_date', sa.Date(), nullable=False),
    sa.Column('score', sa.Float(), nullable=True),
    sa.Column('score_label', sa.String(length=20), nullable=True),
    sa.Column('dimension_scores', sa.Text(), nullable=True),
    sa.Column('signals', sa.Text(), nullable=True),
    sa.Column('max_severity', sa.String(length=10), nullable=False),
    sa.Column('notified', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'stock_code', 'scan_date', name='uq_user_stock_date')
    )
    op.create_index('ix_scan_user_date', 'user_scan_results', ['user_id', 'scan_date'], unique=False)
    op.create_table('user_watchlist',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('stock_code', sa.String(length=20), nullable=False),
    sa.Column('stock_name', sa.String(length=50), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('added_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'stock_code', name='uq_user_stock')
    )
    op.create_index(op.f('ix_user_watchlist_user_id'), 'user_watchlist', ['user_id'], unique=False)


def downgrade() -> None:
    """Drop user_notification_configs, user_scan_results, user_watchlist tables."""
    op.drop_index(op.f('ix_user_watchlist_user_id'), table_name='user_watchlist')
    op.drop_table('user_watchlist')
    op.drop_index('ix_scan_user_date', table_name='user_scan_results')
    op.drop_table('user_scan_results')
    op.drop_table('user_notification_configs')
