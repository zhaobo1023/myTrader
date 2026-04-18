# -*- coding: utf-8 -*-
"""Add agent_conversations and agent_messages tables

Revision ID: y1z2a3b4c5d6
Revises: x1y2z3a4b5c6
Create Date: 2026-04-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'y1z2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'x1y2z3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. agent_conversations
    op.create_table(
        'agent_conversations',
        sa.Column('id', sa.String(36), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(200), nullable=False, server_default=''),
        sa.Column('active_skill', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_agent_conv_user_id', 'agent_conversations', ['user_id'])
    op.create_index('ix_agent_conv_updated_at', 'agent_conversations', ['updated_at'])

    # 2. agent_messages
    op.create_table(
        'agent_messages',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('conversation_id', sa.String(36), nullable=False),
        sa.Column('role', sa.Enum('user', 'assistant', 'tool', name='agent_msg_role'), nullable=False),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('tool_calls', sa.JSON(), nullable=True),
        sa.Column('tool_call_id', sa.String(100), nullable=True),
        sa.Column('tool_name', sa.String(100), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['conversation_id'], ['agent_conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_agent_msg_conversation_id', 'agent_messages', ['conversation_id'])
    op.create_index('ix_agent_msg_created_at', 'agent_messages', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_agent_msg_created_at', table_name='agent_messages')
    op.drop_index('ix_agent_msg_conversation_id', table_name='agent_messages')
    op.drop_table('agent_messages')
    op.drop_index('ix_agent_conv_updated_at', table_name='agent_conversations')
    op.drop_index('ix_agent_conv_user_id', table_name='agent_conversations')
    op.drop_table('agent_conversations')
