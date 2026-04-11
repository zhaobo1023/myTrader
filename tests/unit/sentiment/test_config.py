"""
Test Configuration Module
"""

import pytest
from data_analyst.sentiment.config import (
    VIX_THRESHOLDS,
    US10Y_THRESHOLDS,
    EVENT_KEYWORDS,
    SIGNAL_MAP,
)


def test_vix_thresholds_valid():
    """VIX 阈值配置有效"""
    assert VIX_THRESHOLDS['extreme_calm'] < VIX_THRESHOLDS['normal']
    assert VIX_THRESHOLDS['normal'] < VIX_THRESHOLDS['anxiety']
    assert VIX_THRESHOLDS['anxiety'] < VIX_THRESHOLDS['fear']


def test_us10y_thresholds_valid():
    """US10Y 阈值配置有效"""
    assert US10Y_THRESHOLDS['low'] < US10Y_THRESHOLDS['watershed']
    assert US10Y_THRESHOLDS['watershed'] < US10Y_THRESHOLDS['high']


def test_event_keywords_not_empty():
    """事件关键词库非空"""
    assert len(EVENT_KEYWORDS['bullish']) > 0
    assert len(EVENT_KEYWORDS['bearish']) > 0
    assert len(EVENT_KEYWORDS['policy']) > 0


def test_event_keywords_structure():
    """事件关键词库结构正确"""
    for event_type in ['bullish', 'bearish', 'policy']:
        assert event_type in EVENT_KEYWORDS
        for category, keywords in EVENT_KEYWORDS[event_type].items():
            assert isinstance(keywords, list)
            assert len(keywords) > 0


def test_signal_map_complete():
    """信号映射完整"""
    for event_type in ['bullish', 'bearish', 'policy']:
        assert event_type in SIGNAL_MAP
        for category in EVENT_KEYWORDS[event_type].keys():
            assert category in SIGNAL_MAP[event_type]
            signal_info = SIGNAL_MAP[event_type][category]
            assert 'signal' in signal_info
            assert 'reason' in signal_info
