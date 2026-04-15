"""add llm_feedback table

Revision ID: k1l2m3n4o5p6
Revises: j1k2l3m4n5o6
Create Date: 2026-04-15 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'k1l2m3n4o5p6'
down_revision: Union[str, Sequence[str], None] = 'j1k2l3m4n5o6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'llm_feedback',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('skill_id', sa.String(64), nullable=False, comment='LLM skill identifier'),
        sa.Column('rating', sa.String(16), nullable=False, comment='helpful or unhelpful'),
        sa.Column('user_id', sa.Integer(), nullable=True, comment='User who rated'),
        sa.Column('resource_id', sa.Integer(), nullable=True, comment='Related resource, e.g. theme_id'),
        sa.Column('comment', sa.String(500), nullable=True, comment='Optional free-text comment'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_llm_feedback_skill_id', 'llm_feedback', ['skill_id'])
    op.create_index('ix_llm_feedback_user_id', 'llm_feedback', ['user_id'])
    op.create_index('ix_llm_feedback_rating', 'llm_feedback', ['rating'])


def downgrade() -> None:
    op.drop_index('ix_llm_feedback_rating', table_name='llm_feedback')
    op.drop_index('ix_llm_feedback_user_id', table_name='llm_feedback')
    op.drop_index('ix_llm_feedback_skill_id', table_name='llm_feedback')
    op.drop_table('llm_feedback')
