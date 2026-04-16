"""add trade_article_digest table

Revision ID: r1s2t3u4v5w6
Revises: q1r2s3t4u5v6
Create Date: 2026-04-16 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'r1s2t3u4v5w6'
down_revision: Union[str, Sequence[str], None] = 'q1r2s3t4u5v6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('trade_article_digest',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('article_date', sa.Date(), nullable=False,
                  comment='article publish date'),
        sa.Column('digest_date', sa.Date(), nullable=True,
                  comment='date when digest was generated'),
        sa.Column('source_id', sa.String(length=100), nullable=True,
                  comment='cubox id or dedup key'),
        sa.Column('source_url', sa.String(length=500), nullable=True),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('source_name', sa.String(length=100), nullable=True,
                  comment='public account name'),
        sa.Column('article_type', sa.String(length=30), nullable=True,
                  comment='daily_brief/macro/sector/strategy/opinion'),
        sa.Column('grade', sa.String(length=1), nullable=True,
                  comment='A/B/C/D quality grade from LLM'),
        sa.Column('digest_json', sa.JSON(), nullable=False,
                  comment='structured digest from LLM'),
        sa.Column('summary', sa.String(length=2000), nullable=True,
                  comment='2-sentence summary from deep extraction'),
        sa.Column('used_in_report', sa.Integer(), nullable=True,
                  server_default=sa.text('0'),
                  comment='1 if included in curated report'),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_id', name='uk_source_id'),
        sa.Index('idx_article_date', 'article_date'),
        sa.Index('idx_grade', 'grade'),
    )


def downgrade() -> None:
    op.drop_table('trade_article_digest')
