"""
Test Fear Index Service
"""

import pytest
from data_analyst.sentiment.fear_index import FearIndexService


def test_calculate_fear_greed_score_extreme_fear():
    """VIX > 35 应返回极度恐慌"""
    service = FearIndexService()
    score = service.calculate_fear_greed_score(vix=40, us10y=4.5)
    assert score <= 20  # extreme_fear


def test_calculate_fear_greed_score_extreme_greed():
    """VIX < 15 应返回极度贪婪"""
    service = FearIndexService()
    score = service.calculate_fear_greed_score(vix=12, us10y=3.5)
    assert score >= 80  # extreme_greed


def test_calculate_fear_greed_score_neutral():
    """VIX 20-25 应返回中性"""
    service = FearIndexService()
    score = service.calculate_fear_greed_score(vix=22, us10y=4.0)
    assert 40 <= score <= 60  # neutral range


def test_get_market_regime():
    """市场状态判断正确"""
    service = FearIndexService()
    assert service.get_market_regime(15) == 'extreme_fear'
    assert service.get_market_regime(30) == 'fear'
    assert service.get_market_regime(50) == 'neutral'
    assert service.get_market_regime(70) == 'greed'
    assert service.get_market_regime(85) == 'extreme_greed'


def test_get_vix_level():
    """VIX 级别描述正确"""
    service = FearIndexService()
    assert '极度平静' in service.get_vix_level(12)
    assert '正常' == service.get_vix_level(18)
    assert '焦虑' == service.get_vix_level(22)
    assert '恐慌' == service.get_vix_level(30)
    assert '极度恐慌' == service.get_vix_level(40)


def test_get_us10y_strategy():
    """US10Y 策略建议正确"""
    service = FearIndexService()
    strategy_low = service.get_us10y_strategy(3.5)
    assert '宽松' in strategy_low or '成长股' in strategy_low
    
    strategy_high = service.get_us10y_strategy(4.5)
    assert '价值股' in strategy_high or '防御' in strategy_high
    
    strategy_mid = service.get_us10y_strategy(4.35)
    assert '分水岭' in strategy_mid


def test_check_risk_contagion_both_high():
    """OVX 和 VIX 同时高应触发警报"""
    service = FearIndexService()
    alert = service.check_risk_contagion(vix=30, ovx=60)
    assert alert is not None
    assert '流动性危机' in alert or '共振' in alert


def test_check_risk_contagion_ovx_high_vix_low():
    """OVX 高但 VIX 低应提示能源端风险"""
    service = FearIndexService()
    alert = service.check_risk_contagion(vix=15, ovx=60)
    assert alert is not None
    assert '能源端' in alert


def test_check_risk_contagion_both_low():
    """OVX 和 VIX 都低应无警报"""
    service = FearIndexService()
    alert = service.check_risk_contagion(vix=15, ovx=30)
    assert alert is None


@pytest.mark.integration
def test_fetch_vix_real():
    """实际获取 VIX 数据（需网络）"""
    service = FearIndexService()
    vix = service.fetch_vix()
    assert vix >= 0  # VIX 不应为负数


def test_calculate_fear_greed_score_boundary():
    """测试评分边界值"""
    service = FearIndexService()
    
    # 测试最小值
    score = service.calculate_fear_greed_score(vix=50, us10y=5.0)
    assert score == 0
    
    # 测试最大值
    score = service.calculate_fear_greed_score(vix=10, us10y=3.0)
    assert score == 100


def test_get_vix_level_all_ranges():
    """测试所有 VIX 级别范围"""
    service = FearIndexService()
    
    assert '极度平静' in service.get_vix_level(10)
    assert service.get_vix_level(18) == '正常'
    assert service.get_vix_level(22) == '焦虑'
    assert service.get_vix_level(30) == '恐慌'
    assert service.get_vix_level(40) == '极度恐慌'


def test_get_us10y_strategy_all_ranges():
    """测试所有 US10Y 策略范围"""
    service = FearIndexService()
    
    low_strategy = service.get_us10y_strategy(3.5)
    assert '成长股' in low_strategy
    
    mid_strategy = service.get_us10y_strategy(4.35)
    assert '分水岭' in mid_strategy
    
    high_strategy = service.get_us10y_strategy(4.5)
    assert '价值股' in high_strategy or '防御' in high_strategy


def test_check_risk_contagion_all_scenarios():
    """测试所有风险传导场景"""
    service = FearIndexService()
    
    # 场景1: 两者都高
    alert = service.check_risk_contagion(vix=30, ovx=60)
    assert alert is not None
    assert '共振' in alert
    
    # 场景2: OVX高VIX低
    alert = service.check_risk_contagion(vix=15, ovx=60)
    assert alert is not None
    assert '能源端' in alert
    
    # 场景3: 两者都低
    alert = service.check_risk_contagion(vix=15, ovx=30)
    assert alert is None
    
    # 场景4: VIX高OVX低
    alert = service.check_risk_contagion(vix=30, ovx=30)
    assert alert is None


@pytest.mark.integration
def test_get_fear_index_real():
    """实际获取完整恐慌指数（需网络）"""
    service = FearIndexService()
    result = service.get_fear_index()
    assert result.vix >= 0
    assert result.ovx >= 0
    assert result.gvz >= 0
    assert result.us10y >= 0
    assert 0 <= result.fear_greed_score <= 100
    assert result.market_regime in ['extreme_fear', 'fear', 'neutral', 'greed', 'extreme_greed']
