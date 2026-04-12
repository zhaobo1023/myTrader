"""add preset strategy run table

Revision ID: f1a2b3c4d5e6
Revises: e1f2a3b4c5d6
Create Date: 2026-04-12 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create trade_preset_strategy_run table."""
    op.create_table(
        'trade_preset_strategy_run',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('strategy_key', sa.String(50), nullable=False),
        sa.Column('run_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('triggered_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('signal_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('momentum_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reversal_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('market_status', sa.String(20), nullable=False, server_default=''),
        sa.Column('market_message', sa.String(200), nullable=False, server_default=''),
        sa.Column('signals_json', sa.Text(16777215), nullable=True),
        sa.Column('error_msg', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('strategy_key', 'run_date', name='uq_key_date'),
    )


def downgrade() -> None:
    """Drop trade_preset_strategy_run table."""
    op.drop_table('trade_preset_strategy_run')
