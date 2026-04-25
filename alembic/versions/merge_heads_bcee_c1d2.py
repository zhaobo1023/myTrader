# -*- coding: utf-8 -*-
"""Merge heads: bcee6b766334 (memos FK) + c1d2e3f4g5h6 (tags tables)

Revision ID: d1e2f3a4b5c6
Revises: bcee6b766334, c1d2e3f4g5h6
Create Date: 2026-04-25
"""
from typing import Sequence, Union

revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, Sequence[str]] = ('bcee6b766334', 'c1d2e3f4g5h6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
