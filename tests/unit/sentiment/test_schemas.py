"""
Test Data Models
"""

import pytest
from datetime import datetime
from data_analyst.sentiment.schemas import (
    FearIndexResult,
    NewsItem,
    SentimentResult,
    EventSignal,
    PolymarketEvent,
)


def test_fear_index_result_creation():
    """FearIndexResult 创建正常"""
    result = FearIndexResult(
        vix=25.0,
        ovx=50.0,
        gvz=20.0,
        us10y=4.3,
        fear_greed_score=35,
        market_regime='fear',
        vix_level='恐慌',
        us10y_strategy='分水岭',
        risk_alert=None,
        timestamp=datetime.now()
    )
    assert result.fear_greed_score == 35
    assert result.market_regime == 'fear'


def test_fear_index_result_to_dict():
    """FearIndexResult 可序列化"""
    result = FearIndexResult(
        vix=25.0,
        ovx=50.0,
        gvz=20.0,
        us10y=4.3,
        fear_greed_score=35,
        market_regime='fear',
        vix_level='恐慌',
        us10y_strategy='分水岭',
        risk_alert='测试警报',
        timestamp=datetime.now()
    )
    data = result.to_dict()
    assert isinstance(data, dict)
    assert data['vix'] == 25.0
    assert data['fear_greed_score'] == 35
    assert isinstance(data['timestamp'], str)


def test_news_item_creation():
    """NewsItem 创建正常"""
    news = NewsItem(
        title='比亚迪业绩大增',
        content='比亚迪发布年报...',
        source='东方财富',
        stock_code='002594'
    )
    assert news.title == '比亚迪业绩大增'
    assert news.stock_code == '002594'


def test_sentiment_result_to_dict():
    """SentimentResult 可序列化"""
    news = NewsItem(title='测试新闻', stock_code='000001')
    sentiment = SentimentResult(
        news_item=news,
        sentiment='positive',
        sentiment_strength=4,
        entities=['比亚迪'],
        keywords=['业绩', '增长'],
        summary='业绩利好'
    )
    data = sentiment.to_dict()
    assert isinstance(data, dict)
    assert data['sentiment'] == 'positive'
    assert data['sentiment_strength'] == 4


def test_event_signal_to_dict():
    """EventSignal 可序列化"""
    signal = EventSignal(
        trade_date='2026-04-11',
        stock_code='000001',
        stock_name='平安银行',
        event_type='bullish',
        event_category='资产重组',
        signal='strong_buy',
        signal_reason='资产重组可能带来基本面质变',
        news_title='平安银行重大资产重组',
        matched_keywords=['资产重组']
    )
    data = signal.to_dict()
    assert isinstance(data, dict)
    assert data['signal'] == 'strong_buy'


def test_polymarket_event_to_dict():
    """PolymarketEvent 可序列化"""
    event = PolymarketEvent(
        event_id='123',
        event_title='Will tariffs increase?',
        market_question='Will US impose new tariffs?',
        yes_probability=72.0,
        volume=1200000.0,
        is_smart_money_signal=True,
        category='tariff',
        snapshot_time=datetime.now()
    )
    data = event.to_dict()
    assert isinstance(data, dict)
    assert data['yes_probability'] == 72.0
    assert isinstance(data['snapshot_time'], str)
