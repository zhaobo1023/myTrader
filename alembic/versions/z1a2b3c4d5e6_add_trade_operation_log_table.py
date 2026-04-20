# -*- coding: utf-8 -*-
"""Add trade_operation_logs table

Revision ID: z1a2b3c4d5e6
Revises: y1z2a3b4c5d6
Create Date: 2026-04-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'z1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'y1z2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'trade_operation_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('operation_type', sa.String(20), nullable=False,
                  comment='open_position/add_reduce/close_position/move_to_candidate/manual_note/modify_info'),
        sa.Column('stock_code', sa.String(20), nullable=False, server_default=''),
        sa.Column('stock_name', sa.String(50), nullable=True),
        sa.Column('detail', sa.String(500), nullable=True),
        sa.Column('before_value', sa.String(200), nullable=True),
        sa.Column('after_value', sa.String(200), nullable=True),
        sa.Column('source', sa.String(20), nullable=False, server_default='auto'),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_trade_log_user_id', 'trade_operation_logs', ['user_id'])
    op.create_index('ix_trade_log_user_type', 'trade_operation_logs', ['user_id', 'operation_type'])
    op.create_index('ix_trade_log_created_at', 'trade_operation_logs', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_trade_log_created_at', table_name='trade_operation_logs')
    op.drop_index('ix_trade_log_user_type', table_name='trade_operation_logs')
    op.drop_index('ix_trade_log_user_id', table_name='trade_operation_logs')
    op.drop_table('trade_operation_logs')
