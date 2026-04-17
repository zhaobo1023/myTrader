# -*- coding: utf-8 -*-
"""P1: user_positions table + watchlist multi-tenancy fix

Revision ID: w1x2y3z4a5b6
Revises: v1w2x3y4z5a6
Create Date: 2026-04-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'w1x2y3z4a5b6'
down_revision: Union[str, Sequence[str], None] = 'v1w2x3y4z5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create user_positions table
    op.create_table(
        'user_positions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('stock_code', sa.String(20), nullable=False),
        sa.Column('stock_name', sa.String(50), nullable=True),
        sa.Column('level', sa.String(10), nullable=True),
        sa.Column('shares', sa.Integer(), nullable=True),
        sa.Column('cost_price', sa.Float(), nullable=True),
        sa.Column('account', sa.String(50), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'stock_code', 'account', name='uq_user_position'),
    )
    op.create_index('ix_user_positions_user_id', 'user_positions', ['user_id'])

    # 2. Fix watchlist: drop old unique constraint, add new composite one + FK
    # Note: MySQL requires dropping index by name
    try:
        op.drop_constraint('uq_watchlist_stock', 'user_watchlist', type_='unique')
    except Exception:
        # Constraint may not exist if table was created with old migration
        pass

    op.create_unique_constraint('uq_watchlist_user_stock', 'user_watchlist', ['user_id', 'stock_code'])

    # Add FK if not already present
    try:
        op.create_foreign_key(
            'fk_watchlist_user_id', 'user_watchlist', 'users',
            ['user_id'], ['id'], ondelete='CASCADE',
        )
    except Exception:
        pass


def downgrade() -> None:
    try:
        op.drop_constraint('fk_watchlist_user_id', 'user_watchlist', type_='foreignkey')
    except Exception:
        pass
    try:
        op.drop_constraint('uq_watchlist_user_stock', 'user_watchlist', type_='unique')
    except Exception:
        pass
    op.create_unique_constraint('uq_watchlist_stock', 'user_watchlist', ['stock_code'])
    op.drop_index('ix_user_positions_user_id', table_name='user_positions')
    op.drop_table('user_positions')
