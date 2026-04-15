"""add research_document table

Revision ID: n1o2p3q4r5s6
Revises: m1n2o3p4q5r6
Create Date: 2026-04-15 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'n1o2p3q4r5s6'
down_revision: Union[str, Sequence[str], None] = 'm1n2o3p4q5r6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('research_document',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('file_type', sa.String(length=20), nullable=False,
                  comment='pdf/md/docx/txt'),
        sa.Column('file_size', sa.Integer(), nullable=False,
                  comment='bytes'),
        sa.Column('file_path', sa.String(length=500), nullable=False,
                  comment='server storage path'),
        sa.Column('collection', sa.String(length=50), nullable=False,
                  server_default='research',
                  comment='chromadb collection'),
        sa.Column('tags', sa.String(length=500), nullable=True,
                  comment='comma-separated tags'),
        sa.Column('memo', sa.Text(), nullable=True,
                  comment='user notes about this document'),
        sa.Column('chunk_count', sa.Integer(), nullable=False,
                  server_default='0',
                  comment='number of chunks ingested'),
        sa.Column('status', sa.Enum('pending', 'processing', 'done', 'failed',
                                     name='docstatusenum'),
                  nullable=False, server_default='pending'),
        sa.Column('error_msg', sa.String(length=500), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_status', 'research_document', ['status'])
    op.create_index('idx_collection', 'research_document', ['collection'])
    op.create_index('idx_tags', 'research_document', ['tags'], prefix_length=100)


def downgrade() -> None:
    op.drop_index('idx_tags', table_name='research_document')
    op.drop_index('idx_collection', table_name='research_document')
    op.drop_index('idx_status', table_name='research_document')
    op.drop_table('research_document')
    op.execute("DROP TYPE IF EXISTS docstatusenum")
