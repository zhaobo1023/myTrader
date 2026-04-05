# -*- coding: utf-8 -*-
"""
Portfolio service - holdings aggregation, PnL calculation
"""
import logging
from typing import Optional, List, Dict

from config.db import execute_query

logger = logging.getLogger('myTrader.api')


async def get_portfolio_summary(user_id: int) -> dict:
    """Get aggregated portfolio summary for a user."""
    # Get all active holdings (currently no user_id filter - single user system)
    sql = """
        SELECT h.stock_code, h.stock_name, h.shares, h.cost_price,
               h.account_tag, h.is_margin, h.notes
        FROM model_trade_position h
        WHERE h.status = 1
        ORDER BY h.stock_code
    """
    rows = list(execute_query(sql, ()))

    if not rows:
        return {
            'total_market_value': 0,
            'total_cost': 0,
            'total_pnl': 0,
            'total_pnl_pct': 0,
            'holdings_count': 0,
            'holdings': [],
        }

    holdings = []
    total_mv = 0
    total_cost = 0

    for row in rows:
        code = row['stock_code']
        shares = float(row['shares']) if row['shares'] else 0
        cost = float(row['cost_price']) if row['cost_price'] else 0

        # Get latest close price
        price_sql = """
            SELECT close_price as close
            FROM trade_stock_daily
            WHERE stock_code = %s
            ORDER BY trade_date DESC LIMIT 1
        """
        price_rows = list(execute_query(price_sql, (code,)))
        current_price = float(price_rows[0]['close']) if price_rows else None

        market_value = current_price * shares if current_price else 0
        pnl = (current_price - cost) * shares if current_price else 0
        pnl_pct = ((current_price / cost) - 1) * 100 if cost > 0 and current_price else 0

        holdings.append({
            'stock_code': code,
            'stock_name': row.get('stock_name'),
            'shares': shares,
            'account_tag': row.get('account_tag'),
            'cost_price': cost,
            'current_price': current_price,
            'market_value': round(market_value, 2),
            'pnl': round(pnl, 2),
            'pnl_pct': round(pnl_pct, 2),
        })

        total_mv += market_value
        total_cost += cost * shares

    total_pnl = total_mv - total_cost
    total_pnl_pct = ((total_mv / total_cost) - 1) * 100 if total_cost > 0 else 0

    return {
        'total_market_value': round(total_mv, 2),
        'total_cost': round(total_cost, 2),
        'total_pnl': round(total_pnl, 2),
        'total_pnl_pct': round(total_pnl_pct, 2),
        'holdings_count': len(holdings),
        'holdings': holdings,
    }


async def get_portfolio_history(user_id: int, days: int = 30) -> dict:
    """Get portfolio value history."""
    sql = """
        SELECT d.trade_date,
               SUM(d.close_price * h.shares) as total_value
        FROM model_trade_position h
        JOIN trade_stock_daily d ON h.stock_code = d.stock_code AND d.trade_date >= (
            SELECT MAX(trade_date) - INTERVAL %s DAY FROM trade_stock_daily
        )
        WHERE h.status = 1
        GROUP BY d.trade_date
        ORDER BY d.trade_date
    """
    rows = list(execute_query(sql, (days,)))

    if not rows:
        return {'start_date': '', 'end_date': '', 'count': 0, 'data': []}

    first_value = float(rows[0]['total_value']) if rows[0]['total_value'] else 1

    snapshots = []
    for row in rows:
        val = float(row['total_value']) if row['total_value'] else 0
        pnl = val - first_value
        pnl_pct = ((val / first_value) - 1) * 100 if first_value > 0 else 0
        snapshots.append({
            'date': str(row['trade_date']),
            'total_value': round(val, 2),
            'pnl': round(pnl, 2),
            'pnl_pct': round(pnl_pct, 2),
        })

    return {
        'start_date': str(rows[0]['trade_date']),
        'end_date': str(rows[-1]['trade_date']),
        'count': len(snapshots),
        'data': snapshots,
    }
