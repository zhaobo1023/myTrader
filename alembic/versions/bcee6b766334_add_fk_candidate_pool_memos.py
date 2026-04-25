# -*- coding: utf-8 -*-
"""Add FK constraint on candidate_pool_memos.candidate_stock_id

Revision ID: bcee6b766334
Revises: ef2b16c38708
Create Date: 2026-04-25
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'bcee6b766334'
down_revision: Union[str, None] = 'ef2b16c38708'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_foreign_key(
        'fk_memo_candidate_stock',
        'candidate_pool_memos',
        'candidate_pool_stocks',
        ['candidate_stock_id'],
        ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint('fk_memo_candidate_stock', 'candidate_pool_memos', type_='foreignkey')
