# -*- coding: utf-8 -*-
"""
Unit tests for K-line indicator interpretation logic.

The getInterpretation function (TypeScript) is mirrored here in Python
to allow fast unit testing of the interpretation rules without a browser.
"""
from __future__ import annotations
from typing import Any


# ---------------------------------------------------------------------------
# Mirror of getInterpretation from KLineChart.tsx
# ---------------------------------------------------------------------------

def _interpretation(key: str, period: str, data: list[dict[str, Any]]) -> str | None:
    """Python mirror of getInterpretation() in KLineChart.tsx."""
    if not data:
        return None

    window_label = {'daily': '近5日', 'weekly': '近4周', 'monthly': '近3个月'}.get(period, '近5日')
    n = {'daily': 5, 'weekly': 4, 'monthly': 3}.get(period, 5)
    recent = data[-n:]
    last = data[-1]

    if key == 'ma':
        ma5 = last.get('ma5')
        ma20 = last.get('ma20')
        close = last['close']
        if ma5 is None or ma20 is None:
            return f'MA：{window_label}数据不足，无法判断趋势。'
        above_ma5 = close > ma5
        above_ma20 = close > ma20
        golden_cross = ma5 > ma20
        if above_ma5 and above_ma20 and golden_cross:
            trend = f'收盘价（{close:.2f}）站上MA5（{ma5:.2f}）和MA20（{ma20:.2f}），短期多头排列，趋势偏强。'
        elif not above_ma5 and not above_ma20 and not golden_cross:
            trend = f'收盘价（{close:.2f}）跌破MA5（{ma5:.2f}）和MA20（{ma20:.2f}），短期空头排列，趋势偏弱。'
        elif above_ma5 and not above_ma20:
            trend = f'收盘价（{close:.2f}）站上MA5（{ma5:.2f}）但仍低于MA20（{ma20:.2f}），短期反弹但中期压力仍存。'
        else:
            period_label = {'daily': '日', 'weekly': '周', 'monthly': '月'}.get(period, '日')
            trend = f'均线多空交织，{period_label}K趋势方向尚不明确。'
        return f'MA（{window_label}）：{trend}'

    if key == 'rsi':
        rsi = last.get('rsi_12')
        if rsi is None:
            return f'RSI：{window_label}数据不足。'
        if rsi >= 70:
            level = f'RSI-12（{rsi:.1f}）已进入超买区域（>70），短期注意获利了结风险。'
        elif rsi <= 30:
            level = f'RSI-12（{rsi:.1f}）已进入超卖区域（<30），短期可能存在反弹机会。'
        elif rsi >= 50:
            level = f'RSI-12（{rsi:.1f}）位于强势区间（50-70），多头动能尚存。'
        else:
            level = f'RSI-12（{rsi:.1f}）位于弱势区间（30-50），多头动能偏弱。'
        return f'RSI（{window_label}）：{level}'

    if key == 'kdj':
        k = last.get('kdj_k')
        d = last.get('kdj_d')
        j = last.get('kdj_j')
        if k is None or d is None or j is None:
            return f'KDJ：{window_label}数据不足。'
        if k > d and j > 80:
            sig = f'K（{k:.1f}）上穿D（{d:.1f}），J值（{j:.1f}）偏高，短期存在超买迹象。'
        elif k < d and j < 20:
            sig = f'K（{k:.1f}）下穿D（{d:.1f}），J值（{j:.1f}）偏低，短期可能超卖反弹。'
        elif k > d:
            sig = f'K（{k:.1f}）高于D（{d:.1f}），KDJ呈多头排列，短期偏强。'
        else:
            sig = f'K（{k:.1f}）低于D（{d:.1f}），KDJ呈空头排列，短期偏弱。'
        return f'KDJ（{window_label}）：{sig}'

    if key == 'macd':
        dif = last.get('macd_dif')
        dea = last.get('macd_dea')
        hist = last.get('macd_histogram')
        if dif is None or dea is None or hist is None:
            return f'MACD：{window_label}数据不足。'
        gold_cross = dif > dea
        above_zero = dif > 0
        if gold_cross and above_zero:
            sig = f'DIF（{dif:.3f}）金叉DEA（{dea:.3f}）且位于零轴上方，多头动能强劲。'
        elif gold_cross and not above_zero:
            sig = f'DIF（{dif:.3f}）金叉DEA（{dea:.3f}），但仍处零轴下方，反弹力度待观察。'
        elif not gold_cross and not above_zero:
            sig = f'DIF（{dif:.3f}）死叉DEA（{dea:.3f}）且位于零轴下方，空头动能较强。'
        else:
            sig = f'DIF（{dif:.3f}）死叉DEA（{dea:.3f}），虽在零轴上方但动能走弱。'
        recent_hist = [d['macd_histogram'] for d in recent if d.get('macd_histogram') is not None]
        if len(recent_hist) >= 2:
            hist_trend = '柱状图持续放大' if recent_hist[-1] > recent_hist[0] else '柱状图持续缩小'
        else:
            hist_trend = ''
        return f'MACD（{window_label}）：{sig}' + (f' {hist_trend}。' if hist_trend else '')

    if key == 'boll':
        upper = last.get('boll_upper')
        middle = last.get('boll_middle')
        lower = last.get('boll_lower')
        close = last['close']
        if upper is None or middle is None or lower is None:
            return f'BOLL：{window_label}数据不足。'
        bandwidth = (upper - lower) / middle * 100
        if close > upper:
            pos = f'收盘价（{close:.2f}）突破上轨（{upper:.2f}），短期超买，注意回落风险。'
        elif close < lower:
            pos = f'收盘价（{close:.2f}）跌破下轨（{lower:.2f}），短期超卖，可关注反弹机会。'
        elif close > middle:
            pos = f'收盘价（{close:.2f}）运行在中轨（{middle:.2f}）上方，趋势偏多。'
        else:
            pos = f'收盘价（{close:.2f}）运行在中轨（{middle:.2f}）下方，趋势偏空。'
        narrow = '，布林带收窄，可能面临方向选择。' if bandwidth < 5 else '。'
        return f'BOLL（{window_label}）：{pos} 带宽 {bandwidth:.1f}%{narrow}'

    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bar(**kwargs) -> dict:
    defaults = {
        'close': 10.0, 'open': 9.5, 'high': 10.5, 'low': 9.0, 'volume': 1000,
        'ma5': 10.0, 'ma20': 9.5,
        'rsi_12': 55.0,
        'kdj_k': 60.0, 'kdj_d': 55.0, 'kdj_j': 70.0,
        'macd_dif': 0.05, 'macd_dea': 0.03, 'macd_histogram': 0.02,
        'boll_upper': 11.0, 'boll_middle': 10.0, 'boll_lower': 9.0,
    }
    defaults.update(kwargs)
    return defaults


def _make_data(n=5, **kwargs) -> list:
    return [_make_bar(**kwargs) for _ in range(n)]


# ---------------------------------------------------------------------------
# Tests: empty / missing data
# ---------------------------------------------------------------------------

def test_empty_data_returns_none():
    assert _interpretation('ma', 'daily', []) is None


def test_missing_ma_returns_insufficiency_msg():
    data = _make_data(5, ma5=None, ma20=None)
    result = _interpretation('ma', 'daily', data)
    assert result is not None
    assert '数据不足' in result


def test_missing_rsi_returns_insufficiency_msg():
    data = _make_data(5, rsi_12=None)
    result = _interpretation('rsi', 'daily', data)
    assert '数据不足' in result


def test_missing_kdj_returns_insufficiency_msg():
    data = _make_data(5, kdj_k=None, kdj_d=None, kdj_j=None)
    result = _interpretation('kdj', 'daily', data)
    assert '数据不足' in result


def test_missing_macd_returns_insufficiency_msg():
    data = _make_data(5, macd_dif=None, macd_dea=None, macd_histogram=None)
    result = _interpretation('macd', 'daily', data)
    assert '数据不足' in result


def test_missing_boll_returns_insufficiency_msg():
    data = _make_data(5, boll_upper=None, boll_middle=None, boll_lower=None)
    result = _interpretation('boll', 'daily', data)
    assert '数据不足' in result


# ---------------------------------------------------------------------------
# Tests: MA
# ---------------------------------------------------------------------------

def test_ma_bullish_alignment():
    """close > ma5 > ma20 -> 多头排列"""
    data = _make_data(5, close=12.0, ma5=11.0, ma20=10.0)
    result = _interpretation('ma', 'daily', data)
    assert '多头排列' in result
    assert '趋势偏强' in result


def test_ma_bearish_alignment():
    """close < ma5 < ma20 -> 空头排列"""
    data = _make_data(5, close=8.0, ma5=9.0, ma20=10.0)
    result = _interpretation('ma', 'daily', data)
    assert '空头排列' in result
    assert '趋势偏弱' in result


def test_ma_above_ma5_below_ma20():
    data = _make_data(5, close=9.5, ma5=9.0, ma20=10.0)
    result = _interpretation('ma', 'daily', data)
    assert '中期压力' in result


def test_ma_weekly_label():
    data = _make_data(5, close=12.0, ma5=11.0, ma20=10.0)
    result = _interpretation('ma', 'weekly', data)
    assert '近4周' in result


def test_ma_monthly_label():
    data = _make_data(5, close=12.0, ma5=11.0, ma20=10.0)
    result = _interpretation('ma', 'monthly', data)
    assert '近3个月' in result


# ---------------------------------------------------------------------------
# Tests: RSI
# ---------------------------------------------------------------------------

def test_rsi_overbought():
    data = _make_data(5, rsi_12=75.0)
    result = _interpretation('rsi', 'daily', data)
    assert '超买' in result
    assert '70' in result


def test_rsi_oversold():
    data = _make_data(5, rsi_12=25.0)
    result = _interpretation('rsi', 'daily', data)
    assert '超卖' in result
    assert '30' in result


def test_rsi_strong_zone():
    data = _make_data(5, rsi_12=60.0)
    result = _interpretation('rsi', 'daily', data)
    assert '强势区间' in result


def test_rsi_weak_zone():
    data = _make_data(5, rsi_12=40.0)
    result = _interpretation('rsi', 'daily', data)
    assert '弱势区间' in result


# ---------------------------------------------------------------------------
# Tests: KDJ
# ---------------------------------------------------------------------------

def test_kdj_overbought():
    data = _make_data(5, kdj_k=85.0, kdj_d=80.0, kdj_j=95.0)
    result = _interpretation('kdj', 'daily', data)
    assert '超买' in result


def test_kdj_oversold():
    data = _make_data(5, kdj_k=15.0, kdj_d=18.0, kdj_j=9.0)
    result = _interpretation('kdj', 'daily', data)
    assert '超卖' in result


def test_kdj_bullish():
    data = _make_data(5, kdj_k=65.0, kdj_d=60.0, kdj_j=75.0)
    result = _interpretation('kdj', 'daily', data)
    assert '多头排列' in result


def test_kdj_bearish():
    data = _make_data(5, kdj_k=40.0, kdj_d=50.0, kdj_j=20.0)
    result = _interpretation('kdj', 'daily', data)
    assert '空头排列' in result


# ---------------------------------------------------------------------------
# Tests: MACD
# ---------------------------------------------------------------------------

def test_macd_golden_cross_above_zero():
    data = _make_data(5, macd_dif=0.05, macd_dea=0.03, macd_histogram=0.02)
    result = _interpretation('macd', 'daily', data)
    assert '金叉' in result
    assert '零轴上方' in result


def test_macd_golden_cross_below_zero():
    data = _make_data(5, macd_dif=-0.01, macd_dea=-0.03, macd_histogram=0.02)
    result = _interpretation('macd', 'daily', data)
    assert '金叉' in result
    assert '零轴下方' in result


def test_macd_dead_cross_below_zero():
    data = _make_data(5, macd_dif=-0.05, macd_dea=-0.03, macd_histogram=-0.02)
    result = _interpretation('macd', 'daily', data)
    assert '死叉' in result
    assert '空头' in result


def test_macd_histogram_expanding():
    """Recent histogram growing -> 柱状图持续放大"""
    data = [_make_bar(macd_dif=0.05, macd_dea=0.03, macd_histogram=0.01 * (i + 1))
            for i in range(5)]
    result = _interpretation('macd', 'daily', data)
    assert '放大' in result


def test_macd_histogram_shrinking():
    """Recent histogram shrinking -> 柱状图持续缩小"""
    data = [_make_bar(macd_dif=0.05, macd_dea=0.03, macd_histogram=0.05 - 0.01 * i)
            for i in range(5)]
    result = _interpretation('macd', 'daily', data)
    assert '缩小' in result


# ---------------------------------------------------------------------------
# Tests: BOLL
# ---------------------------------------------------------------------------

def test_boll_above_upper():
    data = _make_data(5, close=12.0, boll_upper=11.0, boll_middle=10.0, boll_lower=9.0)
    result = _interpretation('boll', 'daily', data)
    assert '突破上轨' in result
    assert '超买' in result


def test_boll_below_lower():
    data = _make_data(5, close=8.0, boll_upper=11.0, boll_middle=10.0, boll_lower=9.0)
    result = _interpretation('boll', 'daily', data)
    assert '跌破下轨' in result
    assert '超卖' in result


def test_boll_above_middle():
    data = _make_data(5, close=10.5, boll_upper=11.0, boll_middle=10.0, boll_lower=9.0)
    result = _interpretation('boll', 'daily', data)
    assert '中轨' in result
    assert '偏多' in result


def test_boll_narrow_band():
    """Bandwidth < 5% -> 收窄提示"""
    # bandwidth = (10.2 - 9.8) / 10.0 * 100 = 4%
    data = _make_data(5, close=10.1, boll_upper=10.2, boll_middle=10.0, boll_lower=9.8)
    result = _interpretation('boll', 'daily', data)
    assert '收窄' in result
