# -*- coding: utf-8 -*-
"""Add trade_sector_strength_daily and trade_morning_picks tables

Revision ID: z2a3b4c5d6e7
Revises: z1a2b3c4d5e6
Create Date: 2026-04-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'z2a3b4c5d6e7'
down_revision: Union[str, Sequence[str], None] = 'z1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'trade_sector_strength_daily',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('trade_date', sa.Date(), nullable=False, comment='交易日期'),
        sa.Column('sw_level', sa.SmallInteger(), nullable=False, comment='1=一级 2=二级'),
        sa.Column('sector_code', sa.String(20), nullable=False, comment='申万行业代码'),
        sa.Column('sector_name', sa.String(50), nullable=False, comment='申万行业名称'),
        sa.Column('parent_name', sa.String(50), nullable=True, comment='一级行业名称（仅二级有效）'),
        sa.Column('mom_21', sa.Double(), nullable=True, comment='21日动量(%)'),
        sa.Column('rs_60', sa.Double(), nullable=True, comment='60日相对强度截面排名(0-100)'),
        sa.Column('vol_ratio', sa.Double(), nullable=True, comment='近10日均量/60日均量'),
        sa.Column('composite_score', sa.Double(), nullable=True, comment='综合强度分(0-100)'),
        sa.Column('score_rank', sa.SmallInteger(), nullable=True, comment='综合分排名'),
        sa.Column('phase', sa.String(20), nullable=True,
                  comment='accel_up/decel_up/accel_down/decel_down/neutral'),
        sa.Column('is_inflection', sa.SmallInteger(), nullable=False, server_default='0',
                  comment='是否拐点'),
        sa.Column('inflection_type', sa.String(20), nullable=True,
                  comment='turn_up/turn_down'),
        sa.Column('hist_short', sa.Double(), nullable=True, comment='短期历史分位'),
        sa.Column('hist_long', sa.Double(), nullable=True, comment='长期历史分位'),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('trade_date', 'sw_level', 'sector_code',
                            name='uk_date_level_code'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        comment='申万行业每日强度指标',
    )
    op.create_index('idx_ssd_trade_date', 'trade_sector_strength_daily', ['trade_date'])
    op.create_index('idx_ssd_score_rank', 'trade_sector_strength_daily',
                    ['trade_date', 'sw_level', 'score_rank'])

    op.create_table(
        'trade_morning_picks',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('pick_date', sa.Date(), nullable=False, comment='选股日期'),
        sa.Column('stock_code', sa.String(20), nullable=False, comment='股票代码'),
        sa.Column('stock_name', sa.String(50), nullable=True, comment='股票名称'),
        sa.Column('sw_level1', sa.String(50), nullable=True, comment='申万一级行业'),
        sa.Column('sw_level2', sa.String(50), nullable=True, comment='申万二级行业'),
        sa.Column('sector_score', sa.Double(), nullable=True, comment='所在行业综合分'),
        sa.Column('sector_rank', sa.SmallInteger(), nullable=True, comment='所在行业排名'),
        sa.Column('mom_1m', sa.Double(), nullable=True, comment='1个月动量'),
        sa.Column('mom_3m', sa.Double(), nullable=True, comment='3个月动量'),
        sa.Column('rsi_14', sa.Double(), nullable=True, comment='14日RSI'),
        sa.Column('bias_20', sa.Double(), nullable=True, comment='20日乖离率(%)'),
        sa.Column('vol_20', sa.Double(), nullable=True, comment='20日波动率'),
        sa.Column('turnover_20', sa.Double(), nullable=True, comment='20日平均换手率'),
        sa.Column('pick_score', sa.Double(), nullable=True, comment='综合选股分(0-100)'),
        sa.Column('pick_rank', sa.SmallInteger(), nullable=True, comment='选股排名'),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pick_date', 'stock_code', name='uk_date_code'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
        comment='每日盘前多因子选股结果',
    )
    op.create_index('idx_mp_pick_date', 'trade_morning_picks', ['pick_date'])
    op.create_index('idx_mp_pick_rank', 'trade_morning_picks', ['pick_date', 'pick_rank'])


def downgrade() -> None:
    op.drop_index('idx_mp_pick_rank', table_name='trade_morning_picks')
    op.drop_index('idx_mp_pick_date', table_name='trade_morning_picks')
    op.drop_table('trade_morning_picks')

    op.drop_index('idx_ssd_score_rank', table_name='trade_sector_strength_daily')
    op.drop_index('idx_ssd_trade_date', table_name='trade_sector_strength_daily')
    op.drop_table('trade_sector_strength_daily')
