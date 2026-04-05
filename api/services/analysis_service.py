# -*- coding: utf-8 -*-
"""
Analysis service - technical and fundamental analysis
"""
import logging
from typing import Optional, List, Dict, Any

from config.db import execute_query
from api.services.market_service import _normalize_stock_code, _format_date

logger = logging.getLogger('myTrader.api')


async def get_technical_analysis(stock_code: str) -> dict:
    """Generate technical analysis report for a stock."""
    code = _normalize_stock_code(stock_code)

    # Fetch latest K-line data
    kline_sql = """
        SELECT trade_date, open_price as open, high_price as high,
               low_price as low, close_price as close, volume, turnover_rate
        FROM trade_stock_daily
        WHERE stock_code = %s
        ORDER BY trade_date DESC LIMIT 60
    """
    kline_data = list(execute_query(kline_sql, (code,)))
    if not kline_data:
        return {'stock_code': code, 'trade_date': '', 'signals': [], 'score': 0,
                'summary': 'No data found', 'indicators': {}}

    latest = kline_data[0]
    close = float(latest['close'])
    trade_date = _format_date(latest.get('trade_date', ''))

    # Fetch technical indicators
    ind_sql = """
        SELECT ma5, ma10, ma20, ma60, ma120, ma250,
               macd_dif, macd_dea, macd_histogram,
               rsi_6, rsi_12, rsi_24,
               bollinger_upper, bollinger_middle, bollinger_lower,
               volume_ratio, atr
        FROM trade_technical_indicator
        WHERE stock_code = %s
        ORDER BY trade_date DESC LIMIT 2
    """
    ind_data = list(execute_query(ind_sql, (code,)))

    signals = []
    indicators = {}
    score = 0

    if ind_data:
        curr = ind_data[0]
        prev = ind_data[1] if len(ind_data) > 1 else None
        indicators = {k: float(v) if v is not None else None for k, v in curr.items()}

        # MA analysis
        for period_name in ['ma5', 'ma10', 'ma20', 'ma60']:
            ma_val = curr.get(period_name)
            if ma_val is not None:
                ma_float = float(ma_val)
                if close > ma_float:
                    signals.append({
                        'name': f'{period_name.upper()}',
                        'signal': 'bullish',
                        'description': f'Price above {period_name.upper()} ({ma_float:.2f})',
                    })
                    score += 5
                else:
                    signals.append({
                        'name': f'{period_name.upper()}',
                        'signal': 'bearish',
                        'description': f'Price below {period_name.upper()} ({ma_float:.2f})',
                    })
                    score -= 5

        # MACD analysis
        dif = curr.get('macd_dif')
        dea = curr.get('macd_dea')
        hist = curr.get('macd_histogram')
        if dif is not None and dea is not None:
            if float(dif) > float(dea):
                signals.append({'name': 'MACD', 'signal': 'bullish',
                               'description': 'DIF above DEA'})
                score += 10
            else:
                signals.append({'name': 'MACD', 'signal': 'bearish',
                               'description': 'DIF below DEA'})
                score -= 10

        if prev and hist is not None and prev.get('macd_histogram') is not None:
            if float(hist) > float(prev['macd_histogram']):
                signals.append({'name': 'MACD_MOM', 'signal': 'bullish',
                               'description': 'MACD histogram increasing'})
                score += 5
            else:
                signals.append({'name': 'MACD_MOM', 'signal': 'bearish',
                               'description': 'MACD histogram decreasing'})
                score -= 5

        # RSI analysis
        rsi_6 = curr.get('rsi_6')
        if rsi_6 is not None:
            rsi_val = float(rsi_6)
            if rsi_val > 80:
                signals.append({'name': 'RSI_6', 'signal': 'bearish',
                               'description': f'RSI(6) overbought ({rsi_val:.1f})'})
                score -= 10
            elif rsi_val < 20:
                signals.append({'name': 'RSI_6', 'signal': 'bullish',
                               'description': f'RSI(6) oversold ({rsi_val:.1f})'})
                score += 10
            elif rsi_val > 70:
                signals.append({'name': 'RSI_6', 'signal': 'neutral',
                               'description': f'RSI(6) approaching overbought ({rsi_val:.1f})'})
                score -= 3
            elif rsi_val < 30:
                signals.append({'name': 'RSI_6', 'signal': 'neutral',
                               'description': f'RSI(6) approaching oversold ({rsi_val:.1f})'})
                score += 3

        # Volume ratio
        vol_ratio = curr.get('volume_ratio')
        if vol_ratio is not None:
            indicators['volume_ratio'] = float(vol_ratio)

    # Clamp score
    score = max(-100, min(100, score))

    # Generate summary
    bull_count = sum(1 for s in signals if s['signal'] == 'bullish')
    bear_count = sum(1 for s in signals if s['signal'] == 'bearish')
    if bull_count > bear_count * 1.5:
        summary = 'Overall bullish bias with multiple positive signals'
    elif bear_count > bull_count * 1.5:
        summary = 'Overall bearish bias with multiple negative signals'
    else:
        summary = 'Mixed signals, no clear directional bias'

    return {
        'stock_code': code,
        'trade_date': trade_date,
        'signals': signals,
        'score': score,
        'summary': summary,
        'indicators': indicators,
    }


async def get_fundamental_analysis(stock_code: str) -> dict:
    """Generate fundamental analysis report for a stock."""
    code = _normalize_stock_code(stock_code)

    valuation = []
    profitability = []
    growth = []
    score = 0

    # Fetch valuation factors
    val_sql = """
        SELECT pe_ttm, pb, ps_ttm, market_cap, circ_market_cap
        FROM trade_stock_valuation_factor
        WHERE stock_code = %s
        ORDER BY calc_date DESC LIMIT 1
    """
    val_data = list(execute_query(val_sql, (code,)))
    if val_data:
        v = val_data[0]
        if v.get('pe_ttm') is not None:
            pe = float(v['pe_ttm'])
            valuation.append({'metric': 'PE_TTM', 'value': pe,
                             'description': f'PE ratio: {"Low" if pe < 15 else "Medium" if pe < 30 else "High"}'})
            if pe < 15:
                score += 10
            elif pe > 50:
                score -= 5
        if v.get('pb') is not None:
            pb = float(v['pb'])
            valuation.append({'metric': 'PB', 'value': pb, 'description': f'PB ratio'})
            if pb < 1.5:
                score += 5
        if v.get('market_cap') is not None:
            market_cap = float(v['market_cap'])
            valuation.append({'metric': 'MARKET_CAP', 'value': market_cap,
                             'description': f'Market cap: {market_cap/1e8:.1f}B'})

    # Fetch quality factors
    qual_sql = """
        SELECT roa, current_ratio, debt_ratio, cash_flow_ratio
        FROM trade_stock_quality_factor
        WHERE stock_code = %s
        ORDER BY calc_date DESC LIMIT 1
    """
    qual_data = list(execute_query(qual_sql, (code,)))
    if qual_data:
        q = qual_data[0]
        if q.get('roa') is not None:
            roa = float(q['roa'])
            profitability.append({'metric': 'ROA', 'value': roa,
                                'description': f'Return on assets: {"Good" if roa > 0.05 else "Low"}'})
            if roa > 0.05:
                score += 10
        if q.get('current_ratio') is not None:
            cr = float(q['current_ratio'])
            profitability.append({'metric': 'CURRENT_RATIO', 'value': cr,
                                'description': f'Current ratio: {"Healthy" if cr > 1.5 else "Low"}'})
        if q.get('debt_ratio') is not None:
            dr = float(q['debt_ratio'])
            profitability.append({'metric': 'DEBT_RATIO', 'value': dr,
                                'description': f'Debt ratio: {dr:.1%}'})

    # Fetch extended factors for growth
    ext_sql = """
        SELECT net_profit_growth, revenue_growth
        FROM trade_stock_extended_factor
        WHERE stock_code = %s
        ORDER BY calc_date DESC LIMIT 1
    """
    ext_data = list(execute_query(ext_sql, (code,)))
    if ext_data:
        e = ext_data[0]
        if e.get('net_profit_growth') is not None:
            npg = float(e['net_profit_growth'])
            growth.append({'metric': 'NET_PROFIT_GROWTH', 'value': npg,
                          'description': f'Net profit growth: {npg:.1%}'})
            if npg > 0.2:
                score += 15
            elif npg > 0:
                score += 5
            elif npg < -0.2:
                score -= 10
        if e.get('revenue_growth') is not None:
            rg = float(e['revenue_growth'])
            growth.append({'metric': 'REVENUE_GROWTH', 'value': rg,
                          'description': f'Revenue growth: {rg:.1%}'})

    score = max(-100, min(100, score))

    has_data = valuation or profitability or growth
    if not has_data:
        summary = 'No fundamental data available for this stock'
    elif score > 20:
        summary = 'Fundamentally strong with good valuation and growth metrics'
    elif score < -20:
        summary = 'Fundamental concerns with weak profitability or high valuation'
    else:
        summary = 'Mixed fundamental profile, further analysis recommended'

    return {
        'stock_code': code,
        'valuation': valuation,
        'profitability': profitability,
        'growth': growth,
        'score': score,
        'summary': summary,
    }
