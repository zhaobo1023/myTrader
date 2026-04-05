# -*- coding: utf-8 -*-
"""research tables: fundamental_snapshots, sentiment_scores, sentiment_events, composite_scores, watchlist

Revision ID: a1b2c3d4e5f6
Revises: 9dae0fdb5c83
Create Date: 2026-04-05
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = '9dae0fdb5c83'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('fundamental_snapshots',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(10), nullable=False),
        sa.Column('snap_date', sa.Date(), nullable=False),
        sa.Column('fundamental_score', sa.SmallInteger(), nullable=True),
        sa.Column('pe_ttm', sa.Numeric(8, 2), nullable=True),
        sa.Column('pe_quantile_5yr', sa.Numeric(5, 3), nullable=True),
        sa.Column('pb', sa.Numeric(6, 2), nullable=True),
        sa.Column('pb_quantile_5yr', sa.Numeric(5, 3), nullable=True),
        sa.Column('roe', sa.Numeric(6, 4), nullable=True),
        sa.Column('revenue_yoy', sa.Numeric(6, 4), nullable=True),
        sa.Column('profit_yoy', sa.Numeric(6, 4), nullable=True),
        sa.Column('fcf', sa.Numeric(14, 2), nullable=True),
        sa.Column('net_cash', sa.Numeric(14, 2), nullable=True),
        sa.Column('expected_return_2yr', sa.Numeric(6, 4), nullable=True),
        sa.Column('valuation_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', 'snap_date', name='uk_fundamental_code_date'),
    )
    op.create_index('idx_fundamental_code_date', 'fundamental_snapshots', ['code', 'snap_date'])

    op.create_table('sentiment_scores',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(20), nullable=False),
        sa.Column('score_date', sa.Date(), nullable=False),
        sa.Column('composite_score', sa.SmallInteger(), nullable=True),
        sa.Column('score_fund', sa.SmallInteger(), nullable=True),
        sa.Column('score_price_vol', sa.SmallInteger(), nullable=True),
        sa.Column('score_consensus', sa.SmallInteger(), nullable=True),
        sa.Column('score_sector', sa.SmallInteger(), nullable=True),
        sa.Column('score_macro', sa.SmallInteger(), nullable=True),
        sa.Column('historical_quantile', sa.Numeric(4, 3), nullable=True),
        sa.Column('label', sa.String(20), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_sentiment_score_code_date', 'sentiment_scores', ['code', 'score_date'])

    op.create_table('sentiment_events',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(20), nullable=False),
        sa.Column('event_date', sa.Date(), nullable=False),
        sa.Column('event_text', sa.String(300), nullable=False),
        sa.Column('direction', sa.String(10), nullable=False),
        sa.Column('magnitude', sa.String(10), nullable=False),
        sa.Column('category', sa.String(20), nullable=False),
        sa.Column('is_verified', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('verified_result', sa.String(200), nullable=True),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_sentiment_event_code', 'sentiment_events', ['code'])
    op.create_index('idx_sentiment_event_date', 'sentiment_events', ['event_date'])

    op.create_table('composite_scores',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(20), nullable=False),
        sa.Column('score_date', sa.Date(), nullable=False),
        sa.Column('score_technical', sa.SmallInteger(), nullable=True),
        sa.Column('score_fund_flow', sa.SmallInteger(), nullable=True),
        sa.Column('score_fundamental', sa.SmallInteger(), nullable=True),
        sa.Column('score_sentiment', sa.SmallInteger(), nullable=True),
        sa.Column('score_capital_cycle', sa.SmallInteger(), nullable=True),
        sa.Column('composite_score', sa.SmallInteger(), nullable=True),
        sa.Column('direction', sa.String(20), nullable=True),
        sa.Column('phase', sa.SmallInteger(), nullable=True),
        sa.Column('key_signal', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_composite_code_date', 'composite_scores', ['code', 'score_date'])

    op.create_table('watchlist',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(20), nullable=False),
        sa.Column('name', sa.String(100), nullable=True),
        sa.Column('tier', sa.String(10), server_default='watch', nullable=False),
        sa.Column('industry', sa.String(50), nullable=True),
        sa.Column('added_date', sa.Date(), nullable=True),
        sa.Column('profile_yaml', sa.Text(), nullable=True),
        sa.Column('current_thesis', sa.Text(), nullable=True),
        sa.Column('thesis_updated_at', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uk_watchlist_code'),
    )


def downgrade() -> None:
    op.drop_table('watchlist')
    op.drop_index('idx_composite_code_date', table_name='composite_scores')
    op.drop_table('composite_scores')
    op.drop_index('idx_sentiment_event_date', table_name='sentiment_events')
    op.drop_index('idx_sentiment_event_code', table_name='sentiment_events')
    op.drop_table('sentiment_events')
    op.drop_index('idx_sentiment_score_code_date', table_name='sentiment_scores')
    op.drop_table('sentiment_scores')
    op.drop_index('idx_fundamental_code_date', table_name='fundamental_snapshots')
    op.drop_table('fundamental_snapshots')
