# -*- coding: utf-8 -*-
"""add push_category to trade_article_digest

Revision ID: s1t2u3v4w5x6
Revises: r1s2t3u4v5w6
Create Date: 2026-04-16 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 's1t2u3v4w5x6'
down_revision: Union[str, Sequence[str], None] = 'r1s2t3u4v5w6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'trade_article_digest',
        sa.Column('push_category', sa.String(length=20), nullable=True,
                  comment='macro / broker / other'),
    )
    op.create_index('idx_push_category', 'trade_article_digest', ['push_category'])


def downgrade() -> None:
    op.drop_index('idx_push_category', table_name='trade_article_digest')
    op.drop_column('trade_article_digest', 'push_category')
