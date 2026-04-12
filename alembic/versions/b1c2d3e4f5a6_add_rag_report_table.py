# -*- coding: utf-8 -*-
"""add_rag_report_table

Revision ID: b1c2d3e4f5a6
Revises: e1f2a3b4c5d6
Create Date: 2026-04-13
"""
from alembic import op
import sqlalchemy as sa

revision = 'b1c2d3e4f5a6'
down_revision = ('a2b3c4d5e6f7', '68fd8567e039')
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'trade_rag_report',
        sa.Column('id', sa.Integer(), nullable=False, autoincrement=True),
        sa.Column('stock_code', sa.String(20), nullable=False, comment='Stock code'),
        sa.Column('stock_name', sa.String(50), nullable=True, comment='Stock name'),
        sa.Column('report_type', sa.String(20), nullable=False, default='comprehensive', comment='Report type: comprehensive/fundamental/technical'),
        sa.Column('report_date', sa.Date(), nullable=False, comment='Report generation date'),
        sa.Column('content', sa.Text(length=4294967295), nullable=True, comment='Markdown content (LONGTEXT)'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stock_code', 'report_type', 'report_date', name='uq_rag_report_stock_type_date'),
    )
    op.create_index('ix_rag_report_stock_date', 'trade_rag_report', ['stock_code', 'report_date'])


def downgrade():
    op.drop_index('ix_rag_report_stock_date', table_name='trade_rag_report')
    op.drop_table('trade_rag_report')
