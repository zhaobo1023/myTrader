"""add trade_task_run_log table

Revision ID: o1p2q3r4s5t6
Revises: n1o2p3q4r5s6
Create Date: 2026-04-16 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'o1p2q3r4s5t6'
down_revision: Union[str, Sequence[str], None] = 'n1o2p3q4r5s6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'trade_task_run_log',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('run_date', sa.Date(), nullable=False,
                  comment='运行日期(目标交易日)'),
        sa.Column('task_name', sa.String(length=80), nullable=False,
                  comment='任务标识'),
        sa.Column('task_group', sa.String(length=30), nullable=False,
                  comment='分组: data_fetch / factor / indicator / strategy / report / sentiment'),
        sa.Column('status', sa.String(length=20), nullable=False,
                  comment='running / success / failed / skipped'),
        sa.Column('started_at', sa.DateTime(), nullable=False,
                  comment='开始时间'),
        sa.Column('finished_at', sa.DateTime(), nullable=True,
                  comment='结束时间'),
        sa.Column('duration_ms', sa.Integer(), nullable=True,
                  comment='耗时(毫秒)'),
        sa.Column('record_count', sa.Integer(), nullable=True,
                  comment='产出记录数'),
        sa.Column('error_msg', sa.Text(), nullable=True,
                  comment='失败时的错误信息'),
        sa.Column('detail', sa.JSON(), nullable=True,
                  comment='额外明细'),
        sa.Column('created_at', sa.TIMESTAMP(),
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_date', 'task_name', name='uk_date_task'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        comment='任务运行日志',
    )
    op.create_index('idx_run_date', 'trade_task_run_log', ['run_date'])
    op.create_index('idx_task_name', 'trade_task_run_log', ['task_name'])
    op.create_index('idx_status', 'trade_task_run_log', ['status'])


def downgrade() -> None:
    op.drop_index('idx_status', table_name='trade_task_run_log')
    op.drop_index('idx_task_name', table_name='trade_task_run_log')
    op.drop_index('idx_run_date', table_name='trade_task_run_log')
    op.drop_table('trade_task_run_log')
