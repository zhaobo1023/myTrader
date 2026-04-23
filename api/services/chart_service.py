# -*- coding: utf-8 -*-
"""
Chart Service - K-line data + technical indicators for frontend charts

Reads from trade_stock_daily + trade_technical_indicator tables.
"""
import logging
from typing import Optional

from config.db import execute_query

logger = logging.getLogger('myTrader.chart')


def get_kline_data(
    stock_code: str,
    period: str = 'daily',
    limit: int = 500,
) -> dict:
    """
    Return OHLCV data for a stock.

    Args:
        stock_code: e.g. '600519.SH' or '600519'
        period: 'daily' | 'weekly' | 'monthly'
        limit: max rows to return

    Returns:
        dict with 'stock_code', 'period', 'count', 'data' (list of dicts)
    """
    # Normalize stock_code: if no suffix, try common patterns
    code = stock_code.strip()

    if period == 'weekly':
        sql = _weekly_sql(limit)
    elif period == 'monthly':
        sql = _monthly_sql(limit)
    else:
        sql = _daily_sql(limit)

    try:
        rows = execute_query(sql, (code,), env='online')
        if not rows and '.' not in code:
            # Try with suffix
            for suffix in ('.SH', '.SZ', '.BJ'):
                rows = execute_query(sql, (code + suffix,), env='online')
                if rows:
                    code = code + suffix
                    break

        data = [_row_to_dict(r) for r in rows]
        return {
            'stock_code': code,
            'period': period,
            'count': len(data),
            'data': data,
        }
    except Exception as e:
        logger.error('[chart] get_kline_data error: %s', e)
        return {'stock_code': code, 'period': period, 'count': 0, 'data': []}


def get_technical_indicators(
    stock_code: str,
    limit: int = 500,
) -> dict:
    """
    Return precomputed technical indicators (MA/MACD/RSI/KDJ/BOLL) for a stock.
    """
    code = stock_code.strip()
    sql = """
        SELECT
            trade_date,
            ma5, ma10, ma20, ma60, ma120, ma250,
            macd_dif, macd_dea, macd_histogram,
            rsi_6, rsi_12, rsi_24,
            kdj_k, kdj_d, kdj_j,
            bollinger_upper, bollinger_middle, bollinger_lower,
            atr, volume_ratio, turnover_rate
        FROM trade_technical_indicator
        WHERE stock_code = %s
        ORDER BY trade_date DESC
        LIMIT %s
    """
    try:
        rows = execute_query(sql, (code, limit), env='online')
        if not rows and '.' not in code:
            for suffix in ('.SH', '.SZ', '.BJ'):
                rows = execute_query(sql, (code + suffix, limit), env='online')
                if rows:
                    code = code + suffix
                    break

        # Reverse to chronological order
        data = [_indicator_row_to_dict(r) for r in reversed(rows)]
        return {
            'stock_code': code,
            'count': len(data),
            'data': data,
        }
    except Exception as e:
        logger.error('[chart] get_technical_indicators error: %s', e)
        return {'stock_code': code, 'count': 0, 'data': []}


def get_kline_with_indicators(
    stock_code: str,
    period: str = 'daily',
    limit: int = 500,
) -> dict:
    """
    Return merged K-line + technical indicator data for frontend chart.
    This is the primary endpoint for the K-line chart component.
    """
    kline = get_kline_data(stock_code, period, limit)
    if kline['count'] == 0:
        return kline

    indicators = get_technical_indicators(stock_code, limit)

    # Build date -> indicator lookup
    ind_map = {}
    for item in indicators.get('data', []):
        ind_map[item['date']] = item

    # Merge
    for k in kline['data']:
        d = k['date']
        if d in ind_map:
            ind = ind_map[d]
            k['ma5'] = ind.get('ma5')
            k['ma10'] = ind.get('ma10')
            k['ma20'] = ind.get('ma20')
            k['ma60'] = ind.get('ma60')
            k['ma120'] = ind.get('ma120')
            k['ma250'] = ind.get('ma250')
            k['macd_dif'] = ind.get('macd_dif')
            k['macd_dea'] = ind.get('macd_dea')
            k['macd_histogram'] = ind.get('macd_histogram')
            k['rsi_6'] = ind.get('rsi_6')
            k['rsi_12'] = ind.get('rsi_12')
            k['rsi_24'] = ind.get('rsi_24')
            k['kdj_k'] = ind.get('kdj_k')
            k['kdj_d'] = ind.get('kdj_d')
            k['kdj_j'] = ind.get('kdj_j')
            k['boll_upper'] = ind.get('bollinger_upper')
            k['boll_middle'] = ind.get('bollinger_middle')
            k['boll_lower'] = ind.get('bollinger_lower')
            k['volume_ratio'] = ind.get('volume_ratio')
            k['turnover_rate'] = ind.get('turnover_rate')

    return kline


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------

def _daily_sql(limit: int) -> str:
    return """
        SELECT
            stock_code, trade_date,
            open_price as `open`,
            high_price as high,
            low_price as low,
            close_price as `close`,
            volume, amount, turnover_rate
        FROM trade_stock_daily
        WHERE stock_code = %s
        ORDER BY trade_date DESC
        LIMIT %d
    """ % limit


def _weekly_sql(limit: int) -> str:
    return """
        SELECT
            stock_code,
            YEARWEEK(trade_date, 1) as week_key,
            MIN(trade_date) as trade_date,
            SUBSTRING_INDEX(MIN(CONCAT(trade_date, '_', open_price)), '_', -1) as `open`,
            MAX(high_price) as high,
            MIN(low_price) as low,
            SUBSTRING_INDEX(MAX(CONCAT(trade_date, '_', close_price)), '_', -1) as `close`,
            SUM(volume) as volume,
            SUM(amount) as amount,
            AVG(turnover_rate) as turnover_rate
        FROM trade_stock_daily
        WHERE stock_code = %s
        GROUP BY stock_code, YEARWEEK(trade_date, 1)
        ORDER BY week_key DESC
        LIMIT %d
    """ % limit


def _monthly_sql(limit: int) -> str:
    return """
        SELECT
            stock_code,
            DATE_FORMAT(trade_date, '%%%%Y-%%%%m') as month_key,
            MIN(trade_date) as trade_date,
            SUBSTRING_INDEX(MIN(CONCAT(trade_date, '_', open_price)), '_', -1) as `open`,
            MAX(high_price) as high,
            MIN(low_price) as low,
            SUBSTRING_INDEX(MAX(CONCAT(trade_date, '_', close_price)), '_', -1) as `close`,
            SUM(volume) as volume,
            SUM(amount) as amount,
            AVG(turnover_rate) as turnover_rate
        FROM trade_stock_daily
        WHERE stock_code = %s
        GROUP BY stock_code, DATE_FORMAT(trade_date, '%%%%Y-%%%%m')
        ORDER BY month_key DESC
        LIMIT %d
    """ % limit


def _row_to_dict(row: dict) -> dict:
    """Convert a DB row to frontend-friendly dict."""
    from datetime import date as date_type

    td = row.get('trade_date')
    if isinstance(td, date_type):
        td = td.isoformat()

    return {
        'date': td,
        'open': float(row.get('open') or 0),
        'high': float(row.get('high') or 0),
        'low': float(row.get('low') or 0),
        'close': float(row.get('close') or 0),
        'volume': int(row.get('volume') or 0),
        'amount': float(row.get('amount') or 0),
        'turnover_rate': float(row.get('turnover_rate') or 0),
    }


def _indicator_row_to_dict(row: dict) -> dict:
    """Convert an indicator row to frontend dict."""
    from datetime import date as date_type

    td = row.get('trade_date')
    if isinstance(td, date_type):
        td = td.isoformat()

    result = {'date': td}

    # Float fields with nullable handling
    float_fields = [
        'ma5', 'ma10', 'ma20', 'ma60', 'ma120', 'ma250',
        'macd_dif', 'macd_dea', 'macd_histogram',
        'rsi_6', 'rsi_12', 'rsi_24',
        'kdj_k', 'kdj_d', 'kdj_j',
        'bollinger_upper', 'bollinger_middle', 'bollinger_lower',
        'atr', 'volume_ratio', 'turnover_rate',
    ]
    for f in float_fields:
        v = row.get(f)
        result[f] = float(v) if v is not None else None

    return result
