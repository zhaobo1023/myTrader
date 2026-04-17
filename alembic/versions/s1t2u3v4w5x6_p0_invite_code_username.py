# -*- coding: utf-8 -*-
"""P0: invite_codes table + users table add username/display_name/invited_by, email nullable

Revision ID: s1t2u3v4w5x6
Revises: r1s2t3u4v5w6
Create Date: 2026-04-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 's1t2u3v4w5x6'
down_revision: Union[str, Sequence[str], None] = 'r1s2t3u4v5w6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create invite_codes table
    op.create_table(
        'invite_codes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(32), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('used_by', sa.Integer(), nullable=True),
        sa.Column('max_uses', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('use_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['used_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_invite_codes_code', 'invite_codes', ['code'], unique=True)

    # 2. Add username, display_name, invited_by to users table
    op.add_column('users', sa.Column('username', sa.String(50), nullable=True))
    op.add_column('users', sa.Column('display_name', sa.String(100), nullable=True))
    op.add_column('users', sa.Column('invited_by', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_users_invited_by', 'users', 'users', ['invited_by'], ['id'], ondelete='SET NULL')

    # 3. Backfill username from email for existing rows
    op.execute(
        "UPDATE users SET username = SUBSTRING_INDEX(email, '@', 1) WHERE username IS NULL"
    )

    # 4. Make username NOT NULL + unique index
    op.alter_column('users', 'username', existing_type=sa.String(50), nullable=False)
    op.create_index('ix_users_username', 'users', ['username'], unique=True)

    # 5. Make email nullable (was NOT NULL)
    op.alter_column('users', 'email', existing_type=sa.String(255), nullable=True)

    # 6. Reassign user_id=0 records to user_id=1 (admin) if admin exists
    # This is a best-effort data migration; skip if no admin user yet
    op.execute(
        "UPDATE user_watchlist SET user_id = 1 WHERE user_id = 0 AND EXISTS (SELECT 1 FROM users WHERE id = 1)"
    )
    op.execute(
        "UPDATE user_scan_results SET user_id = 1 WHERE user_id = 0 AND EXISTS (SELECT 1 FROM users WHERE id = 1)"
    )


def downgrade() -> None:
    # Revert user_id reassignment (can't fully undo, but restore column defaults)
    op.alter_column('users', 'email', existing_type=sa.String(255), nullable=False)
    op.drop_index('ix_users_username', table_name='users')
    op.drop_constraint('fk_users_invited_by', 'users', type_='foreignkey')
    op.drop_column('users', 'invited_by')
    op.drop_column('users', 'display_name')
    op.drop_column('users', 'username')
    op.drop_index('ix_invite_codes_code', table_name='invite_codes')
    op.drop_table('invite_codes')
