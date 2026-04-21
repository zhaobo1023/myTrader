# -*- coding: utf-8 -*-
"""
风控扫描器

从 DB 读取持仓/候选池数据，调用 RiskEngine 执行评估，输出结果。

依赖: config.db (myTrader 项目)，在 myTrader 运行环境下使用。
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from .config import RiskConfig
from .engine import RiskEngine
from .models import Decision

logger = logging.getLogger('risk_manager.scanner')


def _query(sql: str, params=None, env: str = 'online'):
    """Wrapper around config.db.execute_query."""
    from config.db import execute_query
    return execute_query(sql, params, env=env)


def _load_positions(user_id: int, env: str = 'online') -> List[dict]:
    """Load active positions for a user."""
    sql = """
        SELECT id, stock_code, stock_name, shares, cost_price, level, account
        FROM user_positions
        WHERE user_id = %s AND is_active = 1
        ORDER BY level, stock_code
    """
    return list(_query(sql, (user_id,), env=env))


def _load_latest_prices(stock_codes: List[str], env: str = 'online') -> Dict[str, dict]:
    """Load latest daily data for given stock codes."""
    if not stock_codes:
        return {}
    placeholders = ','.join(['%s'] * len(stock_codes))
    sql = f"""
        SELECT d.stock_code, d.close_price, d.open_price, d.high_price,
               d.low_price, d.volume, d.trade_date
        FROM trade_stock_daily d
        INNER JOIN (
            SELECT stock_code, MAX(trade_date) as max_date
            FROM trade_stock_daily
            WHERE stock_code IN ({placeholders})
            GROUP BY stock_code
        ) t ON d.stock_code = t.stock_code AND d.trade_date = t.max_date
    """
    rows = _query(sql, tuple(stock_codes), env=env)
    return {r['stock_code']: r for r in rows}


def _load_ohlcv_history(stock_code: str, days: int = 30, env: str = 'online') -> Optional[pd.DataFrame]:
    """Load OHLCV history for ATR calculation."""
    sql = """
        SELECT trade_date as date, open_price as open, high_price as high,
               low_price as low, close_price as close, volume
        FROM trade_stock_daily
        WHERE stock_code = %s
        ORDER BY trade_date DESC
        LIMIT %s
    """
    rows = _query(sql, (stock_code, days), env=env)
    if not rows:
        return None
    df = pd.DataFrame(rows)
    # Convert Decimal columns from MySQL to float
    for col in ('open', 'high', 'low', 'close', 'volume'):
        if col in df.columns:
            df[col] = df[col].astype(float)
    df = df.sort_values('date').reset_index(drop=True)
    return df


def _load_candidate_stocks(env: str = 'online') -> List[dict]:
    """Load active stocks from candidate_pool_stocks."""
    sql = """
        SELECT cs.stock_code, cs.stock_name
        FROM candidate_pool_stocks cs
        JOIN candidate_pools cp ON cs.pool_id = cp.id
        WHERE cp.status = 'active' AND cs.status = 'active'
        ORDER BY cs.stock_code
    """
    return list(_query(sql, env=env))


def _is_st(stock_name: str) -> bool:
    """Check if stock name indicates ST status."""
    if not stock_name:
        return False
    upper = stock_name.upper()
    return 'ST' in upper or '*ST' in upper


def scan_portfolio(user_id: int, env: str = 'online') -> dict:
    """
    Scan a user's portfolio for risk issues.

    Returns:
        {
            'user_id': int,
            'scan_time': str,
            'portfolio_summary': {...},
            'stock_alerts': [...],
            'portfolio_alerts': [...],
        }
    """
    positions = _load_positions(user_id, env=env)
    if not positions:
        return {
            'user_id': user_id,
            'scan_time': datetime.now().isoformat(),
            'portfolio_summary': {'total_positions': 0},
            'stock_alerts': [],
            'portfolio_alerts': [],
        }

    stock_codes = [p['stock_code'] for p in positions]
    latest_prices = _load_latest_prices(stock_codes, env=env)

    # Calculate portfolio value
    total_value = 0.0
    position_values: Dict[str, float] = {}
    for p in positions:
        code = p['stock_code']
        price_info = latest_prices.get(code)
        price = float(price_info['close_price']) if price_info else float(p['cost_price'] or 0)
        shares = int(p['shares'] or 0)
        mv = price * shares
        position_values[code] = mv
        total_value += mv

    # Use actual portfolio size so concentration_limit / single_position_limit
    # don't fire on every single stock with the default max_positions=10.
    n_pos = len(positions)
    config = RiskConfig(
        advisory_mode=True,
        max_positions=max(n_pos + 1, 10),          # avoid per-stock concentration noise
        single_position_limit=max(1.0 / n_pos + 0.05, 0.10),  # adaptive threshold
    )
    engine = RiskEngine(config)

    # Rules that are portfolio-level; skip them in per-stock alerts
    PORTFOLIO_RULES = {'concentration_limit', 'single_position_limit'}

    stock_alerts = []
    for p in positions:
        code = p['stock_code']
        name = p['stock_name'] or ''
        price_info = latest_prices.get(code)
        if not price_info:
            stock_alerts.append({
                'stock_code': code,
                'stock_name': name,
                'level': 'WARN',
                'alerts': ['无法获取最新价格数据'],
            })
            continue

        price = float(price_info['close_price'])
        ohlcv = _load_ohlcv_history(code, days=30, env=env)

        result = engine.check_stock(
            stock_code=code,
            price=price,
            ohlcv_history=ohlcv,
            portfolio_value=total_value or 1_000_000,
            cash=0,
            current_positions=position_values,
            position_count=n_pos,
        )

        alerts = []
        for d in result.decisions:
            if d.decision > Decision.APPROVE and d.rule_name not in PORTFOLIO_RULES:
                alerts.append(f"[{d.decision.name}] {d.rule_name}: {d.reason}")

        # ST check
        if _is_st(name):
            alerts.append("[WARN] st_check: 持有ST股票，注意退市风险")

        if alerts:
            stock_alerts.append({
                'stock_code': code,
                'stock_name': name,
                'level': result.final_decision.name,
                'alerts': alerts,
            })

    # Portfolio-level checks
    portfolio_alerts = []

    # Position count
    if n_pos > 10:
        portfolio_alerts.append(
            f"持仓 {n_pos} 只，偏多，建议控制在 10 只以内"
        )

    # Single-stock concentration (>30% of portfolio)
    if total_value > 0:
        for code, mv in sorted(position_values.items(), key=lambda x: -x[1]):
            pct = mv / total_value
            if pct > 0.30:
                name = next((p['stock_name'] for p in positions if p['stock_code'] == code), code)
                portfolio_alerts.append(
                    f"{code}({name}) 占比 {pct:.1%}，超过 30%"
                )

    # Top-5 concentration
    if total_value > 0 and n_pos >= 5:
        top5_pct = sum(v for _, v in sorted(position_values.items(), key=lambda x: -x[1])[:5]) / total_value
        if top5_pct > 0.70:
            portfolio_alerts.append(f"前5大持仓占比 {top5_pct:.1%}，集中度偏高")

    portfolio_summary = {
        'total_positions': len(positions),
        'total_value': round(total_value, 2),
        'l1_count': sum(1 for p in positions if p.get('level') == 'L1'),
        'l2_count': sum(1 for p in positions if p.get('level') == 'L2'),
        'scan_date': str(latest_prices[stock_codes[0]]['trade_date']) if stock_codes and stock_codes[0] in latest_prices else None,
    }

    return {
        'user_id': user_id,
        'scan_time': datetime.now().isoformat(),
        'portfolio_summary': portfolio_summary,
        'stock_alerts': stock_alerts,
        'portfolio_alerts': portfolio_alerts,
    }


def scan_watchlist(env: str = 'online') -> dict:
    """
    Pre-check candidate pool stocks for buy-side risk.

    Returns:
        {
            'scan_time': str,
            'total': int,
            'alerts': [...],
        }
    """
    candidates = _load_candidate_stocks(env=env)
    if not candidates:
        return {'scan_time': datetime.now().isoformat(), 'total': 0, 'alerts': []}

    stock_codes = [c['stock_code'] for c in candidates]
    latest_prices = _load_latest_prices(stock_codes, env=env)

    engine = RiskEngine(RiskConfig(advisory_mode=True))
    alerts = []

    for c in candidates:
        code = c['stock_code']
        name = c['stock_name'] or ''
        price_info = latest_prices.get(code)
        if not price_info:
            continue

        price = float(price_info['close_price'])
        ohlcv = _load_ohlcv_history(code, days=30, env=env)

        result = engine.check_stock(
            stock_code=code,
            price=price,
            ohlcv_history=ohlcv,
        )

        issues = []
        for d in result.decisions:
            if d.decision > Decision.APPROVE:
                issues.append(f"[{d.decision.name}] {d.rule_name}: {d.reason}")

        if _is_st(name):
            issues.append("[WARN] st_check: ST股票，不建议买入")

        if issues:
            alerts.append({
                'stock_code': code,
                'stock_name': name,
                'level': result.final_decision.name,
                'alerts': issues,
            })

    return {
        'scan_time': datetime.now().isoformat(),
        'total': len(candidates),
        'alerts': alerts,
    }
