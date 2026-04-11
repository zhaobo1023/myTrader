"""add sentiment tables

Revision ID: d1e2f3a4b5c6
Revises: cc8095756cc6
Create Date: 2026-04-11 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, Sequence[str], None] = 'cc8095756cc6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create sentiment monitoring tables."""
    
    # 1. trade_fear_index - 恐慌指数表
    op.create_table('trade_fear_index',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('trade_date', sa.Date(), nullable=False),
        sa.Column('vix', sa.Float(), nullable=False, comment='VIX恐慌指数'),
        sa.Column('ovx', sa.Float(), nullable=False, comment='OVX原油波动率'),
        sa.Column('gvz', sa.Float(), nullable=False, comment='GVZ黄金波动率'),
        sa.Column('us10y', sa.Float(), nullable=False, comment='美国10年期国债收益率'),
        sa.Column('fear_greed_score', sa.Integer(), nullable=False, comment='恐慌贪婪评分0-100'),
        sa.Column('market_regime', sa.String(length=50), nullable=False, comment='市场状态'),
        sa.Column('vix_level', sa.String(length=100), nullable=True, comment='VIX级别描述'),
        sa.Column('us10y_strategy', sa.String(length=200), nullable=True, comment='利率策略建议'),
        sa.Column('risk_alert', sa.Text(), nullable=True, comment='风险传导提示'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('trade_date'),
    )
    op.create_index(op.f('ix_trade_fear_index_trade_date'), 'trade_fear_index', ['trade_date'])
    
    # 2. trade_news_sentiment - 新闻情感表
    op.create_table('trade_news_sentiment',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('stock_code', sa.String(length=20), nullable=True, comment='股票代码'),
        sa.Column('stock_name', sa.String(length=100), nullable=True, comment='股票名称'),
        sa.Column('news_title', sa.String(length=500), nullable=False, comment='新闻标题'),
        sa.Column('news_content', sa.Text(), nullable=True, comment='新闻内容'),
        sa.Column('news_source', sa.String(length=100), nullable=True, comment='新闻来源'),
        sa.Column('news_url', sa.String(length=500), nullable=True, comment='新闻链接'),
        sa.Column('publish_time', sa.DateTime(), nullable=True, comment='发布时间'),
        sa.Column('sentiment', sa.String(length=20), nullable=False, comment='情感倾向'),
        sa.Column('sentiment_strength', sa.Integer(), nullable=False, comment='情感强度1-5'),
        sa.Column('entities', sa.Text(), nullable=True, comment='关键实体'),
        sa.Column('keywords', sa.Text(), nullable=True, comment='关键词'),
        sa.Column('summary', sa.Text(), nullable=True, comment='摘要'),
        sa.Column('market_impact', sa.Text(), nullable=True, comment='市场影响'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_trade_news_sentiment_stock_code'), 'trade_news_sentiment', ['stock_code'])
    op.create_index(op.f('ix_trade_news_sentiment_publish_time'), 'trade_news_sentiment', ['publish_time'])
    op.create_index(op.f('ix_trade_news_sentiment_sentiment'), 'trade_news_sentiment', ['sentiment'])
    
    # 3. trade_event_signal - 事件信号表
    op.create_table('trade_event_signal',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('trade_date', sa.Date(), nullable=False, comment='交易日期'),
        sa.Column('stock_code', sa.String(length=20), nullable=True, comment='股票代码'),
        sa.Column('stock_name', sa.String(length=100), nullable=True, comment='股票名称'),
        sa.Column('event_type', sa.String(length=50), nullable=False, comment='事件类型'),
        sa.Column('event_category', sa.String(length=100), nullable=False, comment='事件类别'),
        sa.Column('signal', sa.String(length=50), nullable=False, comment='交易信号'),
        sa.Column('signal_reason', sa.Text(), nullable=True, comment='信号原因'),
        sa.Column('news_title', sa.String(length=500), nullable=True, comment='新闻标题'),
        sa.Column('matched_keywords', sa.Text(), nullable=True, comment='匹配关键词'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_trade_event_signal_trade_date'), 'trade_event_signal', ['trade_date'])
    op.create_index(op.f('ix_trade_event_signal_stock_code'), 'trade_event_signal', ['stock_code'])
    op.create_index(op.f('ix_trade_event_signal_event_type'), 'trade_event_signal', ['event_type'])
    op.create_index(op.f('ix_trade_event_signal_signal'), 'trade_event_signal', ['signal'])
    
    # 4. trade_polymarket_snapshot - Polymarket快照表
    op.create_table('trade_polymarket_snapshot',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('event_id', sa.String(length=100), nullable=False, comment='事件ID'),
        sa.Column('event_title', sa.String(length=500), nullable=False, comment='事件标题'),
        sa.Column('market_question', sa.Text(), nullable=False, comment='市场问题'),
        sa.Column('yes_probability', sa.Float(), nullable=False, comment='Yes概率'),
        sa.Column('volume', sa.Float(), nullable=False, comment='交易量USD'),
        sa.Column('is_smart_money_signal', sa.Boolean(), nullable=False, comment='是否聪明钱信号'),
        sa.Column('category', sa.String(length=100), nullable=True, comment='类别'),
        sa.Column('snapshot_time', sa.DateTime(), nullable=False, comment='快照时间'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_trade_polymarket_snapshot_event_id'), 'trade_polymarket_snapshot', ['event_id'])
    op.create_index(op.f('ix_trade_polymarket_snapshot_snapshot_time'), 'trade_polymarket_snapshot', ['snapshot_time'])
    op.create_index(op.f('ix_trade_polymarket_snapshot_is_smart_money'), 'trade_polymarket_snapshot', ['is_smart_money_signal'])


def downgrade() -> None:
    """Drop sentiment monitoring tables."""
    op.drop_index(op.f('ix_trade_polymarket_snapshot_is_smart_money'), table_name='trade_polymarket_snapshot')
    op.drop_index(op.f('ix_trade_polymarket_snapshot_snapshot_time'), table_name='trade_polymarket_snapshot')
    op.drop_index(op.f('ix_trade_polymarket_snapshot_event_id'), table_name='trade_polymarket_snapshot')
    op.drop_table('trade_polymarket_snapshot')
    
    op.drop_index(op.f('ix_trade_event_signal_signal'), table_name='trade_event_signal')
    op.drop_index(op.f('ix_trade_event_signal_event_type'), table_name='trade_event_signal')
    op.drop_index(op.f('ix_trade_event_signal_stock_code'), table_name='trade_event_signal')
    op.drop_index(op.f('ix_trade_event_signal_trade_date'), table_name='trade_event_signal')
    op.drop_table('trade_event_signal')
    
    op.drop_index(op.f('ix_trade_news_sentiment_sentiment'), table_name='trade_news_sentiment')
    op.drop_index(op.f('ix_trade_news_sentiment_publish_time'), table_name='trade_news_sentiment')
    op.drop_index(op.f('ix_trade_news_sentiment_stock_code'), table_name='trade_news_sentiment')
    op.drop_table('trade_news_sentiment')
    
    op.drop_index(op.f('ix_trade_fear_index_trade_date'), table_name='trade_fear_index')
    op.drop_table('trade_fear_index')
