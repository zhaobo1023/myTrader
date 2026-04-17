# -*- coding: utf-8 -*-
"""P2: inbox_messages table + notification_config daily report columns

Revision ID: x1y2z3a4b5c6
Revises: w1x2y3z4a5b6
Create Date: 2026-04-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'x1y2z3a4b5c6'
down_revision: Union[str, Sequence[str], None] = 'w1x2y3z4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create inbox_messages table
    op.create_table(
        'inbox_messages',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('message_type', sa.String(30), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('metadata_json', sa.Text(), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_inbox_messages_user_id', 'inbox_messages', ['user_id'])
    op.create_index('ix_inbox_messages_created_at', 'inbox_messages', ['created_at'])
    op.create_index('ix_inbox_user_read_created', 'inbox_messages', ['user_id', 'is_read', 'created_at'])

    # 2. Add daily report columns to user_notification_configs
    op.add_column('user_notification_configs', sa.Column('email_enabled', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('user_notification_configs', sa.Column('daily_report_enabled', sa.Boolean(), nullable=False, server_default='1'))
    op.add_column('user_notification_configs', sa.Column('daily_report_time', sa.String(5), nullable=True, server_default='17:00'))
    op.add_column('user_notification_configs', sa.Column('report_include_watchlist', sa.Boolean(), nullable=False, server_default='1'))
    op.add_column('user_notification_configs', sa.Column('report_include_positions', sa.Boolean(), nullable=False, server_default='1'))


def downgrade() -> None:
    op.drop_column('user_notification_configs', 'report_include_positions')
    op.drop_column('user_notification_configs', 'report_include_watchlist')
    op.drop_column('user_notification_configs', 'daily_report_time')
    op.drop_column('user_notification_configs', 'daily_report_enabled')
    op.drop_column('user_notification_configs', 'email_enabled')
    op.drop_index('ix_inbox_user_read_created', table_name='inbox_messages')
    op.drop_index('ix_inbox_messages_created_at', table_name='inbox_messages')
    op.drop_index('ix_inbox_messages_user_id', table_name='inbox_messages')
    op.drop_table('inbox_messages')
