# -*- coding: utf-8 -*-
"""
Market service - data access layer for market data

Uses the existing config.db module for database queries,
with optional Redis caching for frequently accessed data.
"""
import json
import logging
from typing import Optional, List

from config.db import execute_query
from api.config import settings

logger = logging.getLogger('myTrader.api')

# Cache TTL in seconds
CACHE_TTL = {
    'kline': 300,       # 5 minutes
    'indicator': 300,   # 5 minutes
    'factor': 3600,     # 1 hour
    'rps': 600,         # 10 minutes
    'stock_info': 86400, # 24 hours
}


async def get_kline(
    stock_code: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 120,
) -> dict:
    """Get K-line data for a stock."""
    # Normalize stock code
    code = _normalize_stock_code(stock_code)

    # Build query
    sql = """
        SELECT trade_date, open_price as open, high_price as high,
               low_price as low, close_price as close, volume, amount, turnover_rate
        FROM trade_stock_daily
        WHERE stock_code = %s
    """
    params: list = [code]

    if start_date:
        sql += " AND trade_date >= %s"
        params.append(start_date.replace('-', ''))
    if end_date:
        sql += " AND trade_date <= %s"
        params.append(end_date.replace('-', ''))

    sql += " ORDER BY trade_date DESC LIMIT %s"
    params.append(limit)

    rows = list(execute_query(sql, tuple(params)))

    # Reverse to chronological order
    rows.reverse()

    # Format dates
    for row in rows:
        row['trade_date'] = _format_date(row.get('trade_date', ''))

    return {
        'stock_code': code,
        'count': len(rows),
        'data': rows,
    }


async def get_indicators(
    stock_code: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    indicators: Optional[List[str]] = None,
) -> dict:
    """Get technical indicators for a stock."""
    code = _normalize_stock_code(stock_code)

    sql = """
        SELECT trade_date,
               ma5, ma10, ma20, ma60, ma120, ma250,
               macd_dif, macd_dea, macd_histogram,
               rsi_6, rsi_12, rsi_24,
               kdj_k, kdj_d, kdj_j,
               bollinger_upper, bollinger_middle, bollinger_lower,
               atr, volume_ratio, turnover_rate
        FROM trade_technical_indicator
        WHERE stock_code = %s
    """
    params: list = [code]

    if start_date:
        sql += " AND trade_date >= %s"
        params.append(start_date.replace('-', ''))
    if end_date:
        sql += " AND trade_date <= %s"
        params.append(end_date.replace('-', ''))

    sql += " ORDER BY trade_date DESC LIMIT 500"

    rows = list(execute_query(sql, tuple(params)))
    rows.reverse()

    # Format dates
    for row in rows:
        row['trade_date'] = _format_date(row.get('trade_date', ''))

    # Filter to requested indicators if specified
    if indicators:
        for row in rows:
            keys_to_remove = [
                k for k in row.keys()
                if k not in indicators and k not in ('trade_date',)
            ]
            for k in keys_to_remove:
                del row[k]

    return {
        'stock_code': code,
        'count': len(rows),
        'data': rows,
    }


async def get_factors(
    calc_date: str,
    stock_codes: Optional[List[str]] = None,
) -> dict:
    """Get pre-computed factors for a date."""
    date_str = calc_date.replace('-', '')

    sql = """
        SELECT stock_code, calc_date, close,
               mom_20, mom_60, reversal_5, turnover, vol_ratio,
               price_vol_diverge, volatility_20
        FROM trade_stock_basic_factor
        WHERE calc_date = %s
    """
    params: list = [date_str]

    if stock_codes:
        placeholders = ','.join(['%s'] * len(stock_codes))
        sql += f" AND stock_code IN ({placeholders})"
        params.extend([_normalize_stock_code(c) for c in stock_codes])

    sql += " ORDER BY stock_code"

    rows = list(execute_query(sql, tuple(params)))

    for row in rows:
        row['calc_date'] = _format_date(row.get('calc_date', ''))

    return {
        'calc_date': calc_date,
        'count': len(rows),
        'data': rows,
    }


async def get_rps(
    trade_date: Optional[str] = None,
    window: int = 250,
    top_n: int = 50,
    min_rps: Optional[float] = None,
) -> dict:
    """Get RPS rankings for a date."""
    rps_col = f'rps_{window}'
    valid_windows = [20, 60, 120, 250]
    if window not in valid_windows:
        window = 250
        rps_col = 'rps_250'

    if trade_date:
        date_str = trade_date.replace('-', '')
        sql = f"""
            SELECT stock_code, {rps_col} as rps, rps_slope
            FROM trade_stock_rps
            WHERE trade_date = %s
        """
        params: list = [date_str]
    else:
        # Get latest date
        latest_sql = "SELECT MAX(trade_date) as max_date FROM trade_stock_rps"
        latest_result = list(execute_query(latest_sql))
        if not latest_result or not latest_result[0].get('max_date'):
            return {'trade_date': '', 'window': window, 'count': 0, 'data': []}

        date_str = latest_result[0]['max_date']
        sql = f"""
            SELECT stock_code, {rps_col} as rps, rps_slope
            FROM trade_stock_rps
            WHERE trade_date = %s
        """
        params = [date_str]

    if min_rps is not None:
        sql += f" AND {rps_col} >= %s"
        params.append(min_rps)

    sql += f" ORDER BY {rps_col} DESC LIMIT %s"
    params.append(top_n)

    rows = list(execute_query(sql, tuple(params)))

    return {
        'trade_date': _format_date(date_str),
        'window': window,
        'count': len(rows),
        'data': rows,
    }


async def search_stocks(keyword: str, limit: int = 20) -> dict:
    """Search stocks and ETFs by code or name."""
    keyword_stripped = keyword.strip()
    code_exact = _normalize_stock_code(keyword_stripped.upper())
    code_like = f'%{keyword_stripped}%'

    sql = """
        SELECT stock_code, stock_name, industry
        FROM trade_stock_basic
        WHERE stock_code LIKE %s OR stock_name LIKE %s
        UNION
        SELECT fund_code AS stock_code, fund_name AS stock_name, 'ETF' AS industry
        FROM trade_etf_info
        WHERE fund_code LIKE %s OR fund_name LIKE %s
        ORDER BY
            CASE WHEN stock_code = %s THEN 1
                 WHEN stock_code LIKE %s THEN 2
                 ELSE 3 END
        LIMIT %s
    """
    params = (
        code_like, code_like,
        code_like, code_like,
        code_exact, code_like,
        limit,
    )

    rows = list(execute_query(sql, params))
    return {'count': len(rows), 'data': rows}


async def get_latest_trade_date() -> Optional[str]:
    """Get the latest trading date in the database."""
    sql = "SELECT MAX(trade_date) as max_date FROM trade_stock_daily"
    result = list(execute_query(sql))
    if result and result[0].get('max_date'):
        return _format_date(result[0]['max_date'])
    return None


def _normalize_stock_code(code: str) -> str:
    """Normalize stock code: ensure it has .SH or .SZ suffix."""
    code = code.strip().upper()
    if '.' in code:
        return code
    # Add suffix based on code prefix
    if code.startswith('6'):
        return f'{code}.SH'
    elif code.startswith(('0', '3')):
        return f'{code}.SZ'
    elif code.startswith('8') or code.startswith('4'):
        return f'{code}.BJ'
    return code


def _format_date(date_str: str) -> str:
    """Convert YYYYMMDD to YYYY-MM-DD."""
    if not date_str:
        return ''
    date_str = str(date_str).replace('-', '')
    if len(date_str) == 8:
        return f'{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}'
    return date_str


# ---------------------------------------------------------------------------
# Global Assets
# ---------------------------------------------------------------------------

# Asset configuration: indicator_key -> display metadata
GLOBAL_ASSET_CONFIG = [
    # group, key, name, unit, decimals
    ('commodity', 'gold',       '黄金',           'USD', 2),
    ('commodity', 'wti_oil',    'WTI原油',        'USD', 2),
    ('commodity', 'brent_oil',  '布伦特原油',     'USD', 2),
    ('commodity', 'spgsci',     'S&P商品指数',    '',    2),
    # GSCI 子指数
    ('commodity_idx', 'spgsci_energy',    'GSCI能源',    '',  2),
    ('commodity_idx', 'spgsci_pm',        'GSCI贵金属',  '',  2),
    ('commodity_idx', 'spgsci_ag',        'GSCI农产品',  '',  2),
    ('commodity_idx', 'spgsci_livestock', 'GSCI畜牧',    '',  2),
    ('commodity_idx', 'spgsci_softs',     'GSCI软商品',  '',  2),
    # 单品种期货
    ('futures', 'nat_gas',  '天然气',  'USD', 3),
    ('futures', 'copper',   '铜',      'USD', 3),
    ('futures', 'silver',   '白银',    'USD', 2),
    ('futures', 'wheat',    '小麦',    'USc', 2),
    ('futures', 'corn',     '玉米',    'USc', 2),
    ('futures', 'soybean',  '大豆',    'USc', 2),
    ('rate',      'us_2y_bond', '美债2Y',         '%',   3),
    ('rate',      'us_10y_bond','美债10Y',         '%',   3),
    ('rate',      'us_30y_bond','美债30Y',         '%',   3),
    ('rate',      'us_10y_2y_spread', '10Y-2Y利差', 'bp', 3),
    ('fx',        'dxy',        '美元指数',       '',    2),
    ('fx',        'usdcny',     '美元/人民币',    '',    4),
    ('volatility','vix',        'VIX恐慌指数',    '',    2),
    ('volatility','gvz',        'GVZ黄金波动率',  '',    2),
    ('crypto',    'btc',        '比特币',         'USD', 0),
    ('us_equity', 'spy',        'SPY',            'USD', 2),
    ('us_equity', 'qqq',        'QQQ',            'USD', 2),
    ('us_equity', 'dia',        'DIA',            'USD', 2),
]


async def get_global_assets(days: int = 30) -> dict:
    """
    Return global asset overview: latest value, daily change, and trend sparkline.
    Reads from macro_data table (populated by macro_fetcher).
    """
    from datetime import date as _date, timedelta
    from decimal import Decimal

    keys = [cfg[1] for cfg in GLOBAL_ASSET_CONFIG]
    placeholders = ','.join(['%s'] * len(keys))

    cutoff = (_date.today() - timedelta(days=days + 10)).strftime('%Y-%m-%d')

    sql = f"""
        SELECT indicator, date, value
        FROM macro_data
        WHERE indicator IN ({placeholders})
          AND date >= %s
        ORDER BY indicator, date
    """
    rows = list(execute_query(sql, tuple(keys) + (cutoff,)))

    # Group by indicator
    grouped: dict = {}
    for r in rows:
        key = r['indicator']
        if key not in grouped:
            grouped[key] = []
        v = r['value']
        grouped[key].append({
            'date': r['date'].strftime('%Y-%m-%d') if hasattr(r['date'], 'strftime') else str(r['date']),
            'value': float(v) if v is not None else None,
        })

    assets = []
    for group, key, name, unit, decimals in GLOBAL_ASSET_CONFIG:
        points = grouped.get(key, [])
        if not points:
            assets.append({
                'key': key, 'name': name, 'group': group, 'unit': unit,
                'value': None, 'change': None, 'change_pct': None,
                'date': None, 'trend': [],
            })
            continue

        latest = points[-1]
        prev = points[-2] if len(points) >= 2 else None
        change = None
        change_pct = None
        if prev and prev['value'] and latest['value']:
            change = round(latest['value'] - prev['value'], decimals)
            if prev['value'] != 0:
                change_pct = round((latest['value'] - prev['value']) / abs(prev['value']) * 100, 2)

        # Sparkline: take last N days of points
        trend = [p['value'] for p in points[-days:] if p['value'] is not None]

        assets.append({
            'key': key,
            'name': name,
            'group': group,
            'unit': unit,
            'value': round(latest['value'], decimals) if latest['value'] is not None else None,
            'change': change,
            'change_pct': change_pct,
            'date': latest['date'],
            'trend': trend,
        })

    # Group assets
    groups = {}
    GROUP_NAMES = {
        'commodity': '商品', 'rate': '利率', 'fx': '汇率',
        'volatility': '波动率', 'crypto': '加密货币', 'us_equity': '美股ETF',
        'commodity_idx': '商品子指数', 'futures': '大宗期货',
    }
    for a in assets:
        g = a['group']
        if g not in groups:
            groups[g] = {'name': GROUP_NAMES.get(g, g), 'items': []}
        groups[g]['items'].append(a)

    return {'groups': list(groups.values()), 'updated': _date.today().strftime('%Y-%m-%d')}
