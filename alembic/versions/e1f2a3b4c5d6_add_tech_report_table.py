"""add tech report table

Revision ID: e1f2a3b4c5d6
Revises: d1e2f3a4b5c6
Create Date: 2026-04-12 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create trade_tech_report table."""
    op.create_table(
        'trade_tech_report',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('stock_code', sa.String(20), nullable=False),
        sa.Column('stock_name', sa.String(50), nullable=False, server_default=''),
        sa.Column('trade_date', sa.Date(), nullable=False),
        sa.Column('score', sa.Float(), nullable=False, server_default='0'),
        sa.Column('score_label', sa.String(20), nullable=False, server_default=''),
        sa.Column('max_severity', sa.String(10), nullable=False, server_default='NONE'),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('signals', sa.Text(16777215), nullable=False, comment='JSON list'),
        sa.Column('indicators', sa.Text(16777215), nullable=False, comment='JSON dict'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stock_code', 'trade_date', name='uq_code_date'),
    )


def downgrade() -> None:
    """Drop trade_tech_report table."""
    op.drop_table('trade_tech_report')
