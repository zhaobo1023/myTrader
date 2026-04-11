"""
Test Sentiment Storage Service
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch
from data_analyst.sentiment.storage import SentimentStorage
from data_analyst.sentiment.schemas import (
    FearIndexResult,
    NewsItem,
    SentimentResult,
    EventSignal,
    PolymarketEvent,
)


@pytest.fixture
def fear_index_result():
    """创建测试用的恐慌指数结果"""
    return FearIndexResult(
        vix=25.0,
        ovx=50.0,
        gvz=20.0,
        us10y=4.3,
        fear_greed_score=35,
        market_regime='fear',
        vix_level='恐慌',
        us10y_strategy='分水岭',
        risk_alert=None,
        timestamp=datetime.now(),
    )


@pytest.fixture
def sentiment_results():
    """创建测试用的情感分析结果"""
    news = NewsItem(
        title='测试新闻',
        content='测试内容',
        stock_code='000001',
    )
    return [
        SentimentResult(
            news_item=news,
            sentiment='positive',
            sentiment_strength=4,
            entities=['公司A'],
            keywords=['利好', '增长'],
            summary='业绩利好',
        )
    ]


@pytest.fixture
def event_signals():
    """创建测试用的事件信号"""
    return [
        EventSignal(
            trade_date='2026-04-11',
            stock_code='000001',
            stock_name='测试股票',
            event_type='bullish',
            event_category='资产重组',
            signal='strong_buy',
            signal_reason='资产重组可能带来基本面质变',
            news_title='公司重大资产重组',
            matched_keywords=['资产重组'],
        )
    ]


@patch('data_analyst.sentiment.storage.execute_insert')
def test_save_fear_index(mock_insert, fear_index_result):
    """测试保存恐慌指数"""
    storage = SentimentStorage(env='local')
    result = storage.save_fear_index(fear_index_result)
    
    assert result is True
    assert mock_insert.called
    call_args = mock_insert.call_args
    assert 'INSERT INTO trade_fear_index' in call_args[0][0]


@patch('data_analyst.sentiment.storage.execute_query')
def test_get_fear_index_history(mock_query):
    """测试获取恐慌指数历史"""
    mock_query.return_value = [
        {
            'vix': 25.0,
            'ovx': 50.0,
            'gvz': 20.0,
            'us10y': 4.3,
            'fear_greed_score': 35,
            'market_regime': 'fear',
            'vix_level': '恐慌',
            'us10y_strategy': '分水岭',
            'risk_alert': None,
            'created_at': datetime.now(),
        }
    ]
    
    storage = SentimentStorage(env='local')
    history = storage.get_fear_index_history(days=7)
    
    assert len(history) == 1
    assert history[0]['vix'] == 25.0
    assert mock_query.called


@patch('data_analyst.sentiment.storage.execute_batch_insert')
def test_save_news_sentiment(mock_batch_insert, sentiment_results):
    """测试保存新闻情感"""
    storage = SentimentStorage(env='local')
    result = storage.save_news_sentiment(sentiment_results)
    
    assert result is True
    assert mock_batch_insert.called


@patch('data_analyst.sentiment.storage.execute_batch_insert')
def test_save_event_signals(mock_batch_insert, event_signals):
    """测试保存事件信号"""
    storage = SentimentStorage(env='local')
    result = storage.save_event_signals(event_signals)
    
    assert result is True
    assert mock_batch_insert.called


@patch('data_analyst.sentiment.storage.execute_batch_insert')
def test_save_empty_list(mock_batch_insert):
    """测试保存空列表"""
    storage = SentimentStorage(env='local')
    result = storage.save_news_sentiment([])
    
    assert result is True
    assert not mock_batch_insert.called


@patch('data_analyst.sentiment.storage.execute_query')
def test_get_recent_events(mock_query):
    """测试获取最近事件"""
    mock_query.return_value = [
        {
            'trade_date': '2026-04-11',
            'stock_code': '000001',
            'stock_name': '测试股票',
            'event_type': 'bullish',
            'event_category': '资产重组',
            'signal': 'strong_buy',
            'signal_reason': '资产重组可能带来基本面质变',
            'news_title': '公司重大资产重组',
            'matched_keywords': '资产重组',
            'created_at': datetime.now(),
        }
    ]
    
    storage = SentimentStorage(env='local')
    events = storage.get_recent_events(days=3, event_type='bullish')
    
    assert len(events) == 1
    assert events[0]['event_type'] == 'bullish'
    assert mock_query.called
