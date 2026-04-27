# -*- coding: utf-8 -*-
"""
Chart Service - K-line data + technical indicators for frontend charts

Reads from trade_stock_daily + trade_technical_indicator tables.
"""
import logging
from datetime import date as date_type

from config.db import execute_query

logger = logging.getLogger('myTrader.chart')


def _resolve_stock_code(code: str) -> str:
    """
    If code has no suffix (e.g. '600519'), try .SH/.SZ/.BJ against trade_stock_daily.
    Returns the resolved code (with suffix) or the original if no match.
    """
    if '.' in code:
        return code
    for suffix in ('.SH', '.SZ', '.BJ'):
        rows = execute_query(
            'SELECT 1 FROM trade_stock_daily WHERE stock_code = %s LIMIT 1',
            (code + suffix,),
            env='online',
        )
        if rows:
            return code + suffix
    return code


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
    code = stock_code.strip()
    sql = _period_sql(period)

    try:
        code = _resolve_stock_code(code)
        rows = execute_query(sql, (code, limit), env='online')
        # Return in chronological (ASC) order for frontend charts
        data = [_row_to_dict(r) for r in reversed(rows)]
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
        code = _resolve_stock_code(code)
        rows = execute_query(sql, (code, limit), env='online')
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

    For weekly/monthly periods, each K-line bar carries the indicator values
    of its **last** trading day (the day whose close price equals the bar's
    close).  This ensures the indicators reflect the period-end state.
    """
    kline = get_kline_data(stock_code, period, limit)
    if kline['count'] == 0:
        return kline

    # For weekly/monthly we need more daily indicator rows than the
    # number of aggregated bars (1 week ~ 5 daily rows).
    ind_limit = limit if period == 'daily' else limit * 6
    indicators = get_technical_indicators(kline['stock_code'], ind_limit)

    # Build date -> indicator lookup
    ind_map = {}
    for item in indicators.get('data', []):
        ind_map[item['date']] = item

    _merge_fields = (
        'ma5', 'ma10', 'ma20', 'ma60', 'ma120', 'ma250',
        'macd_dif', 'macd_dea', 'macd_histogram',
        'rsi_6', 'rsi_12', 'rsi_24',
        'kdj_k', 'kdj_d', 'kdj_j',
        'bollinger_upper', 'bollinger_middle', 'bollinger_lower',
        'volume_ratio', 'turnover_rate',
    )
    _rename = {
        'bollinger_upper': 'boll_upper',
        'bollinger_middle': 'boll_middle',
        'bollinger_lower': 'boll_lower',
    }

    if period == 'daily':
        # Direct date match
        for k in kline['data']:
            ind = ind_map.get(k['date'])
            if not ind:
                continue
            for f in _merge_fields:
                k[_rename.get(f, f)] = ind.get(f)
    else:
        # For weekly/monthly bars, match indicators by the bar's
        # last_trade_date (period-end date) instead of the bar's date
        # (period-start date).
        for k in kline['data']:
            last_date = k.get('last_trade_date')
            ind = ind_map.get(last_date) if last_date else None
            if not ind:
                # Fallback: try the bar's own date (period-start)
                ind = ind_map.get(k['date'])
            if not ind:
                continue
            for f in _merge_fields:
                k[_rename.get(f, f)] = ind.get(f)

    return kline


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------

def _period_sql(period: str) -> str:
    """Return SQL for the given period. Uses parameterized LIMIT %s."""
    if period == 'weekly':
        return _WEEKLY_SQL
    if period == 'monthly':
        return _MONTHLY_SQL
    return _DAILY_SQL


_DAILY_SQL = """
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
    LIMIT %s
"""

_WEEKLY_SQL = """
    SELECT
        stock_code,
        YEARWEEK(trade_date, 1) as week_key,
        MIN(trade_date) as trade_date,
        MAX(trade_date) as last_trade_date,
        (SELECT open_price FROM trade_stock_daily t2
         WHERE t2.stock_code = t1.stock_code
           AND YEARWEEK(t2.trade_date, 1) = YEARWEEK(t1.trade_date, 1)
         ORDER BY t2.trade_date ASC LIMIT 1) as `open`,
        MAX(high_price) as high,
        MIN(low_price) as low,
        (SELECT close_price FROM trade_stock_daily t2
         WHERE t2.stock_code = t1.stock_code
           AND YEARWEEK(t2.trade_date, 1) = YEARWEEK(t1.trade_date, 1)
         ORDER BY t2.trade_date DESC LIMIT 1) as `close`,
        SUM(volume) as volume,
        SUM(amount) as amount,
        AVG(turnover_rate) as turnover_rate
    FROM trade_stock_daily t1
    WHERE stock_code = %s
    GROUP BY stock_code, YEARWEEK(trade_date, 1)
    ORDER BY week_key DESC
    LIMIT %s
"""

_MONTHLY_SQL = """
    SELECT
        stock_code,
        DATE_FORMAT(trade_date, '%%Y-%%m') as month_key,
        MIN(trade_date) as trade_date,
        MAX(trade_date) as last_trade_date,
        (SELECT open_price FROM trade_stock_daily t2
         WHERE t2.stock_code = t1.stock_code
           AND DATE_FORMAT(t2.trade_date, '%%Y-%%m') = DATE_FORMAT(t1.trade_date, '%%Y-%%m')
         ORDER BY t2.trade_date ASC LIMIT 1) as `open`,
        MAX(high_price) as high,
        MIN(low_price) as low,
        (SELECT close_price FROM trade_stock_daily t2
         WHERE t2.stock_code = t1.stock_code
           AND DATE_FORMAT(t2.trade_date, '%%Y-%%m') = DATE_FORMAT(t1.trade_date, '%%Y-%%m')
         ORDER BY t2.trade_date DESC LIMIT 1) as `close`,
        SUM(volume) as volume,
        SUM(amount) as amount,
        AVG(turnover_rate) as turnover_rate
    FROM trade_stock_daily t1
    WHERE stock_code = %s
    GROUP BY stock_code, DATE_FORMAT(trade_date, '%%Y-%%m')
    ORDER BY month_key DESC
    LIMIT %s
"""


def _row_to_dict(row: dict) -> dict:
    """Convert a DB row to frontend-friendly dict."""
    td = row.get('trade_date')
    if isinstance(td, date_type):
        td = td.isoformat()

    def _float(v):
        return float(v) if v is not None else None

    result = {
        'date': td,
        'open': _float(row.get('open')),
        'high': _float(row.get('high')),
        'low': _float(row.get('low')),
        'close': _float(row.get('close')),
        'volume': int(row['volume']) if row.get('volume') is not None else 0,
        'amount': _float(row.get('amount')),
        'turnover_rate': _float(row.get('turnover_rate')),
    }

    # For weekly/monthly aggregated rows, include the last trading date of
    # the period so that indicators can be matched by period-end date.
    ltd = row.get('last_trade_date')
    if ltd is not None:
        if isinstance(ltd, date_type):
            ltd = ltd.isoformat()
        result['last_trade_date'] = ltd

    return result


def _indicator_row_to_dict(row: dict) -> dict:
    """Convert an indicator row to frontend dict."""
    td = row.get('trade_date')
    if isinstance(td, date_type):
        td = td.isoformat()

    result = {'date': td}

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
