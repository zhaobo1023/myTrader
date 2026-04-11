"""
Test Event Detector Service
"""

import pytest
from data_analyst.sentiment.event_detector import EventDetector
from data_analyst.sentiment.schemas import NewsItem


def test_match_keywords_bullish():
    """匹配利好关键词"""
    detector = EventDetector()
    matches = detector.match_keywords('公司发布资产重组公告', 'bullish')
    assert '资产重组' in matches


def test_match_keywords_bearish():
    """匹配利空关键词"""
    detector = EventDetector()
    matches = detector.match_keywords('公司股东减持股份', 'bearish')
    assert '减持' in matches


def test_get_event_category():
    """获取事件类别"""
    detector = EventDetector()
    category = detector.get_event_category('资产重组', 'bullish')
    assert category == '资产重组'


def test_generate_signal_strong_buy():
    """资产重组应生成强烈买入信号"""
    detector = EventDetector()
    signal = detector.generate_signal('bullish', '资产重组')
    assert signal['signal'] == 'strong_buy'
    assert '基本面质变' in signal['reason']


def test_generate_signal_sell():
    """股东减持应生成卖出信号"""
    detector = EventDetector()
    signal = detector.generate_signal('bearish', '股东减持')
    assert signal['signal'] == 'sell'


def test_detect_events():
    """事件检测完整流程"""
    detector = EventDetector()
    news = [
        NewsItem(title='某公司重大资产重组', stock_code='000001'),
        NewsItem(title='今日天气晴朗', stock_code=None),
        NewsItem(title='某公司股东减持', stock_code='000002'),
    ]
    events = detector.detect_events(news)
    assert len(events) >= 2
    event_types = [e.event_type for e in events]
    assert 'bullish' in event_types
    assert 'bearish' in event_types


def test_filter_by_signal():
    """按信号类型过滤"""
    detector = EventDetector()
    news = [
        NewsItem(title='某公司重大资产重组', stock_code='000001'),
        NewsItem(title='某公司股东减持', stock_code='000002'),
    ]
    events = detector.detect_events(news)
    buy_events = detector.filter_by_signal(events, ['strong_buy', 'buy'])
    assert all(e.signal in ['strong_buy', 'buy'] for e in buy_events)


def test_filter_by_event_type():
    """按事件类型过滤"""
    detector = EventDetector()
    news = [
        NewsItem(title='某公司重大资产重组', stock_code='000001'),
        NewsItem(title='某公司股东减持', stock_code='000002'),
    ]
    events = detector.detect_events(news)
    bullish_events = detector.filter_by_event_type(events, ['bullish'])
    assert all(e.event_type == 'bullish' for e in bullish_events)
