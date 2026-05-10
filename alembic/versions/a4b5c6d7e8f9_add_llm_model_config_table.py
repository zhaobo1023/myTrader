# -*- coding: utf-8 -*-
"""Add llm_model_config table

Revision ID: a4b5c6d7e8f9
Revises: z3a4b5c6d7e8
Create Date: 2026-05-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a4b5c6d7e8f9'
down_revision: Union[str, Sequence[str], None] = 'z3a4b5c6d7e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'llm_model_config',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('scene', sa.String(64), nullable=False, comment='Usage scene identifier'),
        sa.Column('alias', sa.String(64), nullable=False, comment='Model alias e.g. qwen, deepseek'),
        sa.Column('model', sa.String(128), nullable=False, comment='Model name e.g. qwen3.6-plus, deepseek-chat'),
        sa.Column('base_url', sa.String(512), nullable=False),
        sa.Column('api_key_env', sa.String(64), nullable=False),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('scene'),
    )

    # Seed default configs for each scene
    op.bulk_insert(
        sa.table(
            'llm_model_config',
            sa.column('scene', sa.String),
            sa.column('alias', sa.String),
            sa.column('model', sa.String),
            sa.column('base_url', sa.String),
            sa.column('api_key_env', sa.String),
            sa.column('is_default', sa.Boolean),
            sa.column('enabled', sa.Boolean),
        ),
        [
            {
                'scene': 'agent_chat',
                'alias': 'qwen',
                'model': 'qwen3.6-plus',
                'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
                'api_key_env': 'RAG_API_KEY',
                'is_default': True,
                'enabled': True,
            },
            {
                'scene': 'rag_query',
                'alias': 'qwen',
                'model': 'qwen3.6-plus',
                'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
                'api_key_env': 'RAG_API_KEY',
                'is_default': True,
                'enabled': True,
            },
            {
                'scene': 'skill',
                'alias': 'qwen',
                'model': 'qwen3.6-plus',
                'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
                'api_key_env': 'RAG_API_KEY',
                'is_default': True,
                'enabled': True,
            },
            {
                'scene': 'report',
                'alias': 'qwen',
                'model': 'qwen3.6-plus',
                'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
                'api_key_env': 'RAG_API_KEY',
                'is_default': True,
                'enabled': True,
            },
            {
                'scene': 'daily_report',
                'alias': 'qwen',
                'model': 'qwen3.6-plus',
                'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
                'api_key_env': 'RAG_API_KEY',
                'is_default': True,
                'enabled': True,
            },
        ],
    )


def downgrade() -> None:
    op.drop_table('llm_model_config')
