"""
Test Polymarket Service
"""

import pytest
from data_analyst.sentiment.polymarket import PolymarketService


def test_parse_market_response():
    """解析市场响应"""
    service = PolymarketService()
    mock_data = {
        'id': '123',
        'title': 'Test Market',
        'question': 'Will tariffs increase?',
        'outcomePrices': '[0.72, 0.28]',
        'volume': '1200000',
        'category': 'politics',
    }
    result = service.parse_market(mock_data)
    assert result is not None
    assert result.yes_probability == 72.0
    assert result.volume == 1200000.0
    assert result.event_id == '123'


def test_detect_smart_money_high_volume_extreme_prob():
    """高交易量+极端概率应识别为聪明钱"""
    service = PolymarketService()
    is_smart = service._detect_smart_money(yes_probability=75.0, volume=2000000)
    assert is_smart is True


def test_detect_smart_money_low_volume():
    """低交易量不应识别为聪明钱"""
    service = PolymarketService()
    is_smart = service._detect_smart_money(yes_probability=75.0, volume=500000)
    assert is_smart is False


def test_detect_smart_money_moderate_prob():
    """中等概率不应识别为聪明钱"""
    service = PolymarketService()
    is_smart = service._detect_smart_money(yes_probability=55.0, volume=2000000)
    assert is_smart is False


@pytest.mark.integration
def test_search_markets_real():
    """实际搜索市场（需网络）"""
    service = PolymarketService()
    markets = service.search_markets('tariff', min_volume=100000)
    assert isinstance(markets, list)
