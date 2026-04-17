# -*- coding: utf-8 -*-
"""add trade_article_report table

Revision ID: t1u2v3w4x5y6
Revises: s1t2u3v4w5x6
Create Date: 2026-04-17 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 't1u2v3w4x5y6'
down_revision: Union[str, Sequence[str], None] = 's1t2u3v4w5x6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('trade_article_report',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('report_date', sa.Date(), nullable=False,
                  comment='report target date'),
        sa.Column('report_type', sa.String(length=30), nullable=False,
                  comment='combined / macro / broker / other'),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('content', sa.Text(), nullable=False,
                  comment='generated markdown report'),
        sa.Column('article_count', sa.Integer(), nullable=True,
                  comment='number of source articles'),
        sa.Column('document_id', sa.String(length=100), nullable=True,
                  comment='feishu document id'),
        sa.Column('doc_url', sa.String(length=500), nullable=True,
                  comment='feishu document url'),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('report_date', 'report_type', name='uk_date_type'),
    )


def downgrade() -> None:
    op.drop_table('trade_article_report')
