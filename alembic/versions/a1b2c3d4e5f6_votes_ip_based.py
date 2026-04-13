"""votes ip based

Convert theme_pool_votes from user_id to voter_ip (IP-based voting).

Revision ID: a1b2c3d4e5f6
Revises: h1i2j3k4l5m6
Create Date: 2026-04-13 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'a1b2c3d4e5f6'
down_revision = 'h1i2j3k4l5m6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop old unique constraint and foreign key
    op.drop_constraint('uq_stock_user_vote', 'theme_pool_votes', type_='unique')
    op.drop_constraint('theme_pool_votes_ibfk_2', 'theme_pool_votes', type_='foreignkey')

    # Drop user_id column, add voter_ip column
    op.drop_column('theme_pool_votes', 'user_id')
    op.add_column('theme_pool_votes', sa.Column('voter_ip', sa.String(45), nullable=False, server_default='127.0.0.1'))

    # Add new unique constraint
    op.create_unique_constraint('uq_stock_ip_vote', 'theme_pool_votes', ['theme_stock_id', 'voter_ip'])


def downgrade() -> None:
    # Drop IP-based constraint and column
    op.drop_constraint('uq_stock_ip_vote', 'theme_pool_votes', type_='unique')
    op.drop_column('theme_pool_votes', 'voter_ip')

    # Re-add user_id column
    op.add_column('theme_pool_votes', sa.Column('user_id', sa.Integer(), nullable=False, server_default='1'))
    op.create_foreign_key('theme_pool_votes_ibfk_2', 'theme_pool_votes', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_unique_constraint('uq_stock_user_vote', 'theme_pool_votes', ['theme_stock_id', 'user_id'])
