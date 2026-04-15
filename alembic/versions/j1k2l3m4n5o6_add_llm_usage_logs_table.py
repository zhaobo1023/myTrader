"""add llm_usage_logs table

Revision ID: j1k2l3m4n5o6
Revises: i1j2k3l4m5n6
Create Date: 2026-04-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'j1k2l3m4n5o6'
down_revision: Union[str, Sequence[str], None] = 'i1j2k3l4m5n6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'llm_usage_logs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('skill_id', sa.String(64), nullable=False, comment='LLM skill identifier, e.g. theme-create'),
        sa.Column('model', sa.String(64), nullable=False, comment='Model alias used, e.g. qwen3-max'),
        sa.Column('latency_ms', sa.Integer(), nullable=False, default=0, comment='Wall-clock latency in milliseconds'),
        sa.Column('user_id', sa.Integer(), nullable=True, comment='User who triggered the skill'),
        sa.Column('resource_id', sa.Integer(), nullable=True, comment='Related resource id, e.g. theme_id'),
        sa.Column('prompt_tokens', sa.Integer(), nullable=False, default=0),
        sa.Column('completion_tokens', sa.Integer(), nullable=False, default=0),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_llm_usage_logs_skill_id', 'llm_usage_logs', ['skill_id'])
    op.create_index('ix_llm_usage_logs_user_id', 'llm_usage_logs', ['user_id'])
    op.create_index('ix_llm_usage_logs_created_at', 'llm_usage_logs', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_llm_usage_logs_created_at', table_name='llm_usage_logs')
    op.drop_index('ix_llm_usage_logs_user_id', table_name='llm_usage_logs')
    op.drop_index('ix_llm_usage_logs_skill_id', table_name='llm_usage_logs')
    op.drop_table('llm_usage_logs')
