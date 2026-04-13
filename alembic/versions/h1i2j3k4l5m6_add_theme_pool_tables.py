"""add theme pool tables

Revision ID: h1i2j3k4l5m6
Revises: g1h2i3j4k5l6
Create Date: 2026-04-13 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'h1i2j3k4l5m6'
down_revision: Union[str, Sequence[str], None] = ('g1h2i3j4k5l6', 'b1c2d3e4f5a6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- theme_pools
    op.create_table(
        'theme_pools',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.Enum('draft', 'active', 'archived', name='themestatus'), nullable=False, server_default='draft'),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    # -- theme_pool_stocks
    op.create_table(
        'theme_pool_stocks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('theme_id', sa.Integer(), nullable=False),
        sa.Column('stock_code', sa.String(20), nullable=False),
        sa.Column('stock_name', sa.String(50), nullable=False, server_default=''),
        sa.Column('recommended_by', sa.Integer(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('entry_price', sa.Double(), nullable=True),
        sa.Column('entry_date', sa.Date(), nullable=False),
        sa.Column('human_status', sa.Enum('normal', 'focused', 'watching', 'excluded', name='humanstatus'), nullable=False, server_default='normal'),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('added_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['theme_id'], ['theme_pools.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['recommended_by'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('theme_id', 'stock_code', name='uq_theme_stock'),
    )
    op.create_index('ix_theme_pool_stocks_theme_id', 'theme_pool_stocks', ['theme_id'])

    # -- theme_pool_scores
    op.create_table(
        'theme_pool_scores',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('theme_stock_id', sa.Integer(), nullable=False),
        sa.Column('score_date', sa.Date(), nullable=False),
        sa.Column('rps_20', sa.Double(), nullable=True),
        sa.Column('rps_60', sa.Double(), nullable=True),
        sa.Column('rps_120', sa.Double(), nullable=True),
        sa.Column('rps_250', sa.Double(), nullable=True),
        sa.Column('tech_score', sa.Double(), nullable=True),
        sa.Column('tech_signals', sa.Text(), nullable=True),
        sa.Column('fundamental_score', sa.Double(), nullable=True),
        sa.Column('fundamental_data', sa.Text(), nullable=True),
        sa.Column('total_score', sa.Double(), nullable=True),
        sa.Column('return_5d', sa.Double(), nullable=True),
        sa.Column('return_10d', sa.Double(), nullable=True),
        sa.Column('return_20d', sa.Double(), nullable=True),
        sa.Column('return_60d', sa.Double(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['theme_stock_id'], ['theme_pool_stocks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('theme_stock_id', 'score_date', name='uq_stock_score_date'),
    )
    op.create_index('ix_theme_pool_scores_date', 'theme_pool_scores', ['score_date'])

    # -- theme_pool_votes
    op.create_table(
        'theme_pool_votes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('theme_stock_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('vote', sa.SmallInteger(), nullable=False),
        sa.Column('voted_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['theme_stock_id'], ['theme_pool_stocks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('theme_stock_id', 'user_id', name='uq_stock_user_vote'),
    )


def downgrade() -> None:
    op.drop_table('theme_pool_votes')
    op.drop_index('ix_theme_pool_scores_date', 'theme_pool_scores')
    op.drop_table('theme_pool_scores')
    op.drop_index('ix_theme_pool_stocks_theme_id', 'theme_pool_stocks')
    op.drop_table('theme_pool_stocks')
    op.drop_table('theme_pools')
    op.execute("DROP TYPE IF EXISTS themestatus")
    op.execute("DROP TYPE IF EXISTS humanstatus")
