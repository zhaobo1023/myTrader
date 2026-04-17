# -*- coding: utf-8 -*-
"""
Portfolio Management Service

Handles:
- CRUD for portfolio_stock
- Return / trigger price calculations
- Market four-factor scoring
- Pure-Python optimizer (no scipy dependency)
- Optimizer run persistence
"""
import json
import logging
from typing import List, Dict, Any, Optional

from config.db import execute_query, execute_update

logger = logging.getLogger('myTrader.api')


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row) -> dict:
    """Convert DB row to plain dict with Decimal -> float conversion."""
    d = dict(row)
    for k, v in list(d.items()):
        try:
            from decimal import Decimal
            if isinstance(v, Decimal):
                d[k] = float(v)
        except ImportError:
            pass
    return d


def list_stocks(user_id: int) -> List[dict]:
    """Return all portfolio stocks for user, joined with latest market cap."""
    sql = """
        SELECT
            ps.id,
            ps.user_id,
            ps.stock_code,
            ps.stock_name,
            ps.industry,
            ps.tier,
            ps.status,
            ps.position_pct,
            ps.profit_26,
            ps.profit_27,
            ps.pe_26,
            ps.pe_27,
            ps.net_cash_26,
            ps.net_cash_27,
            ps.cash_adj_coef,
            ps.equity_adj,
            ps.asset_growth_26,
            ps.asset_growth_27,
            ps.payout_ratio,
            ps.research_depth,
            ps.notes,
            ps.updated_at,
            b.total_mv AS market_cap
        FROM portfolio_stock ps
        LEFT JOIN (
            SELECT stock_code, total_mv
            FROM trade_stock_daily_basic
            WHERE trade_date = (
                SELECT MAX(trade_date) FROM trade_stock_daily_basic
            )
        ) b ON b.stock_code = ps.stock_code
        WHERE ps.user_id = %s
        ORDER BY ps.position_pct DESC, ps.stock_code
    """
    rows = execute_query(sql, (user_id,))
    return [_row_to_dict(r) for r in rows]


def get_stock(stock_code: str, user_id: int) -> Optional[dict]:
    """Get a single portfolio stock by code."""
    sql = """
        SELECT
            ps.*,
            b.total_mv AS market_cap
        FROM portfolio_stock ps
        LEFT JOIN (
            SELECT stock_code, total_mv
            FROM trade_stock_daily_basic
            WHERE trade_date = (
                SELECT MAX(trade_date) FROM trade_stock_daily_basic
            )
        ) b ON b.stock_code = ps.stock_code
        WHERE ps.user_id = %s AND ps.stock_code = %s
    """
    rows = list(execute_query(sql, (user_id, stock_code)))
    return _row_to_dict(rows[0]) if rows else None


def upsert_stock(data: dict, user_id: int) -> dict:
    """Insert or update a portfolio stock. Returns the resulting record."""
    sql = """
        INSERT INTO portfolio_stock
            (user_id, stock_code, stock_name, industry, tier, status,
             position_pct, profit_26, profit_27, pe_26, pe_27,
             net_cash_26, net_cash_27, cash_adj_coef, equity_adj,
             asset_growth_26, asset_growth_27, payout_ratio, research_depth, notes)
        VALUES
            (%s, %s, %s, %s, %s, %s,
             %s, %s, %s, %s, %s,
             %s, %s, %s, %s,
             %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            stock_name      = VALUES(stock_name),
            industry        = VALUES(industry),
            tier            = VALUES(tier),
            status          = VALUES(status),
            position_pct    = VALUES(position_pct),
            profit_26       = VALUES(profit_26),
            profit_27       = VALUES(profit_27),
            pe_26           = VALUES(pe_26),
            pe_27           = VALUES(pe_27),
            net_cash_26     = VALUES(net_cash_26),
            net_cash_27     = VALUES(net_cash_27),
            cash_adj_coef   = VALUES(cash_adj_coef),
            equity_adj      = VALUES(equity_adj),
            asset_growth_26 = VALUES(asset_growth_26),
            asset_growth_27 = VALUES(asset_growth_27),
            payout_ratio    = VALUES(payout_ratio),
            research_depth  = VALUES(research_depth),
            notes           = VALUES(notes),
            updated_at      = CURRENT_TIMESTAMP
    """
    params = (
        user_id,
        data['stock_code'],
        data.get('stock_name', ''),
        data.get('industry', ''),
        data.get('tier', ''),
        data.get('status', 'hold'),
        data.get('position_pct', 0),
        data.get('profit_26'),
        data.get('profit_27'),
        data.get('pe_26'),
        data.get('pe_27'),
        data.get('net_cash_26', 0),
        data.get('net_cash_27', 0),
        data.get('cash_adj_coef', 0.5),
        data.get('equity_adj', 0),
        data.get('asset_growth_26', 0),
        data.get('asset_growth_27', 0),
        data.get('payout_ratio', 0),
        data.get('research_depth', 80),
        data.get('notes'),
    )
    execute_update(sql, params)
    return get_stock(data['stock_code'], user_id) or {}


def delete_stock(stock_code: str, user_id: int) -> bool:
    """Delete a stock from portfolio. Returns True if found and deleted."""
    check_sql = "SELECT id FROM portfolio_stock WHERE user_id = %s AND stock_code = %s"
    rows = list(execute_query(check_sql, (user_id, stock_code)))
    if not rows:
        return False
    execute_update(
        "DELETE FROM portfolio_stock WHERE user_id = %s AND stock_code = %s",
        (user_id, stock_code),
    )
    return True


def get_latest_optimizer_run(user_id: int) -> Optional[dict]:
    """Get most recent optimizer run for user."""
    sql = """
        SELECT id, run_at, result_json, metrics_json
        FROM portfolio_optimizer_run
        WHERE user_id = %s
        ORDER BY run_at DESC LIMIT 1
    """
    rows = list(execute_query(sql, (user_id,)))
    if not rows:
        return None
    r = _row_to_dict(rows[0])
    r['result'] = json.loads(r['result_json'])
    r['metrics'] = json.loads(r['metrics_json'])
    return r


def list_optimizer_runs(user_id: int, limit: int = 10) -> List[dict]:
    """List recent optimizer runs."""
    sql = """
        SELECT id, run_at, metrics_json
        FROM portfolio_optimizer_run
        WHERE user_id = %s
        ORDER BY run_at DESC LIMIT %s
    """
    rows = execute_query(sql, (user_id, limit))
    result = []
    for r in rows:
        d = _row_to_dict(r)
        d['metrics'] = json.loads(d['metrics_json'])
        del d['metrics_json']
        result.append(d)
    return result


def save_optimizer_run(
    input_snapshot: list,
    result: dict,
    metrics: dict,
    user_id: int,
) -> int:
    """Persist optimizer run, return new row id."""
    sql = """
        INSERT INTO portfolio_optimizer_run
            (user_id, input_snapshot, result_json, metrics_json)
        VALUES (%s, %s, %s, %s)
    """
    execute_update(sql, (
        user_id,
        json.dumps(input_snapshot, ensure_ascii=False),
        json.dumps(result, ensure_ascii=False),
        json.dumps(metrics, ensure_ascii=False),
    ))
    rows = list(execute_query("SELECT LAST_INSERT_ID() AS id"))
    return int(rows[0]['id']) if rows else 0


# ---------------------------------------------------------------------------
# Return calculations
# ---------------------------------------------------------------------------

def calc_tgt(stock: dict, year: str = '27') -> float:
    """
    Target market cap for a given year:
    TGT = profit * pe + equity_adj + asset_growth + net_cash * cash_adj_coef
    All inputs in 100M CNY.
    """
    profit = float(stock.get(f'profit_{year}') or 0)
    pe = float(stock.get(f'pe_{year}') or 0)
    equity_adj = float(stock.get('equity_adj') or 0)
    asset_growth = float(stock.get(f'asset_growth_{year}') or 0)
    net_cash = float(stock.get(f'net_cash_{year}') or 0)
    cash_coef = float(stock.get('cash_adj_coef') or 0.5)
    return profit * pe + equity_adj + asset_growth + net_cash * cash_coef


def calc_return_27(stock: dict, market_cap: Optional[float]) -> Optional[float]:
    """
    2027E return (not annualized, total over 2 years):
    return = TGT27/market_cap - 1 + div_26 + div_27
    where div_year = payout_ratio * profit_year / market_cap
    """
    if not market_cap or market_cap <= 0:
        return None
    payout = float(stock.get('payout_ratio') or 0)
    profit_26 = float(stock.get('profit_26') or 0)
    profit_27 = float(stock.get('profit_27') or 0)
    div_26 = payout * profit_26 / market_cap
    div_27 = payout * profit_27 / market_cap
    tgt27 = calc_tgt(stock, '27')
    if tgt27 <= 0:
        return None
    return tgt27 / market_cap - 1 + div_26 + div_27


def calc_growth_27(stock: dict) -> Optional[float]:
    """Profit growth rate 2026->2027 in %."""
    p26 = stock.get('profit_26')
    p27 = stock.get('profit_27')
    if p26 is not None and p27 is not None and float(p26) != 0:
        return (float(p27) - float(p26)) / abs(float(p26)) * 100
    return None


# ---------------------------------------------------------------------------
# Market four-factor scoring
# ---------------------------------------------------------------------------

def calc_market_factors(
    stock: dict,
    market_cap: Optional[float],
    all_stocks: List[dict],
) -> dict:
    """
    Four market factors:
    - valuation  (0-30): undervaluation degree vs implied PE
    - business   (0-30): growth quality
    - liquidity  (0-20): market cap size preference
    - industry_pref (0-20): industry concentration penalty
    Returns dict: {valuation, business, liquidity, industry_pref, total}
    """
    pe_27 = float(stock.get('pe_27') or 0)
    profit_27 = float(stock.get('profit_27') or 0)

    # Valuation factor (0-30): lower implied PE vs fair PE => more undervalued => higher score
    val_score = 0.0
    if market_cap and profit_27 > 0 and pe_27 > 0:
        implied_pe = market_cap / profit_27
        if implied_pe > 0:
            # underval_ratio > 0 means market PE > fair PE (undervalued... wait, that's overvalued)
            # if implied_pe < pe_27 => market is pricing it BELOW fair => undervalued
            underval_ratio = (pe_27 - implied_pe) / pe_27
            val_score = max(0.0, min(30.0, underval_ratio * 30.0))

    # Business factor (0-30)
    g27 = calc_growth_27(stock)
    if g27 is None:
        bus_score = 10.0
    elif g27 >= 20:
        bus_score = 30.0
    elif g27 >= 10:
        bus_score = 20.0 + (g27 - 10) * 1.0
    elif g27 >= 0:
        bus_score = 10.0 + g27 * 1.0
    else:
        bus_score = max(0.0, 10.0 + g27 * 0.5)

    # Liquidity factor (0-20)
    liq_score = 12.0
    if market_cap:
        if market_cap >= 500:
            liq_score = 20.0
        elif market_cap >= 200:
            liq_score = 12.0 + (market_cap - 200) / 300.0 * 8.0
        else:
            liq_score = 12.0
        # Penalize overseas listings slightly
        code = stock.get('stock_code', '')
        if '.' in code:
            liq_score *= 0.95

    # Industry preference factor (0-20): the more concentrated the industry, the lower
    my_industry = stock.get('industry', '')
    my_code = stock.get('stock_code', '')
    industry_total = sum(
        float(s.get('position_pct') or 0)
        for s in all_stocks
        if s.get('industry') == my_industry and s.get('stock_code') != my_code
    )
    market_coef = min(1.0, 0.70 + 0.375 * industry_total / 100.0)
    ind_score = 20.0 * (1.0 - market_coef * 0.5)

    total = val_score + bus_score + liq_score + ind_score
    return {
        'valuation': round(val_score, 2),
        'business': round(bus_score, 2),
        'liquidity': round(liq_score, 2),
        'industry_pref': round(ind_score, 2),
        'total': round(total, 2),
    }


def calc_adj_return(return_27: Optional[float], factors: dict) -> Optional[float]:
    """Adjusted return = return_27 * (factors.total / 100)."""
    if return_27 is None:
        return None
    factor_score = factors.get('total', 0) / 100.0
    return return_27 * factor_score


# ---------------------------------------------------------------------------
# Trigger prices
# ---------------------------------------------------------------------------

def calc_trigger_prices(stock: dict, market_cap: Optional[float]) -> dict:
    """
    Four trigger price thresholds.
    signal: STRONG_BUY | ADD | HOLD | REDUCE | CLEAR | NO_DATA
    """
    tgt27 = calc_tgt(stock, '27')
    payout = float(stock.get('payout_ratio') or 0)
    profit_26 = float(stock.get('profit_26') or 0)
    profit_27 = float(stock.get('profit_27') or 0)

    if tgt27 <= 0 or not market_cap or market_cap <= 0:
        return {
            'tgt_27': round(tgt27, 2),
            'strong_buy': None,
            'add': None,
            'reduce': None,
            'clear': None,
            'signal': 'NO_DATA',
            'signal_label': 'No Data',
        }

    dy = payout * (profit_26 + profit_27) / market_cap

    strong_buy  = tgt27 / max(1.50 - dy, 0.01)
    add_price    = tgt27 / max(1.35 - dy, 0.01)
    reduce_price = tgt27 / max(1.15 - dy, 0.01)
    clear_price  = tgt27 / max(1.05 - dy, 0.01)

    if market_cap <= strong_buy:
        signal = 'STRONG_BUY'
        signal_label = 'Strong Buy'
    elif market_cap <= add_price:
        signal = 'ADD'
        signal_label = 'Add'
    elif market_cap < reduce_price:
        signal = 'HOLD'
        signal_label = 'Hold'
    elif market_cap < clear_price:
        signal = 'REDUCE'
        signal_label = 'Reduce'
    else:
        signal = 'CLEAR'
        signal_label = 'Clear'

    return {
        'tgt_27': round(tgt27, 2),
        'strong_buy': round(strong_buy, 2),
        'add': round(add_price, 2),
        'reduce': round(reduce_price, 2),
        'clear': round(clear_price, 2),
        'signal': signal,
        'signal_label': signal_label,
    }


# ---------------------------------------------------------------------------
# Optimizer (pure Python, no scipy)
# ---------------------------------------------------------------------------

def run_optimizer(stocks_with_returns: List[dict]) -> dict:
    """
    Portfolio optimizer without external solver.

    Strategy: work in integer percentage space (0-100 total invested).
    Constraints are applied greedily, with the remainder becoming cash.

    Constraints:
    - 8-12 stocks (relaxed if insufficient eligible)
    - Each stock <= 25%
    - Industry <= 40%
    - Far Ahead tier >= 60% (if any exist)
    - Leading tier <= 30%
    - Cash fills remainder

    Returns:
        allocations: {stock_code: int_pct}
        cash_pct: int
        constraints_met: bool
        violations: List[str]
    """
    # Step 1: Filter eligible candidates
    eligible = [
        s for s in stocks_with_returns
        if (s.get('return_27') or 0) > 0.03
        and (s.get('research_depth') or 0) >= 60
        and (s.get('adj_return') or 0) > 0.02
    ]

    if len(eligible) < 3:
        eligible = [s for s in stocks_with_returns if (s.get('return_27') or 0) > 0]

    eligible.sort(key=lambda x: x.get('adj_return') or 0, reverse=True)
    candidates = eligible[:15]

    if not candidates:
        return {
            'allocations': {},
            'cash_pct': 100,
            'constraints_met': False,
            'violations': ['No eligible stocks found'],
        }

    n = len(candidates)

    # Step 2: Initial integer allocations proportional to adj_return (sum to 95)
    adj_returns = [max(float(s.get('adj_return') or 0), 0.001) for s in candidates]
    total_adj = sum(adj_returns)
    # Start with 95% invested; allocate proportionally then round
    TARGET = 95
    raw = [r / total_adj * TARGET for r in adj_returns]
    int_w = [max(1, int(r)) for r in raw]
    # Trim to TARGET
    while sum(int_w) > TARGET:
        # Reduce the stock with most excess (allocated - raw)
        excess_idx = max(range(n), key=lambda i: int_w[i] - raw[i])
        if int_w[excess_idx] > 1:
            int_w[excess_idx] -= 1
        else:
            break

    # Step 3: Apply hard caps iteratively
    MAX_STOCK = 25
    MAX_INDUSTRY = 40
    ITERATIONS = 50

    for _ in range(ITERATIONS):
        changed = False

        # Cap individual stocks at 25%
        for i in range(n):
            if int_w[i] > MAX_STOCK:
                excess = int_w[i] - MAX_STOCK
                int_w[i] = MAX_STOCK
                # Redistribute to best under-allocated peers
                candidates_order = sorted(
                    [j for j in range(n) if j != i and int_w[j] < MAX_STOCK],
                    key=lambda j: raw[j],
                    reverse=True,
                )
                for k in range(excess):
                    if candidates_order:
                        int_w[candidates_order[k % len(candidates_order)]] += 1
                changed = True

        # Cap industries at 40%
        ind_idxs: Dict[str, List[int]] = {}
        for i, s in enumerate(candidates):
            ind = s.get('industry', '')
            ind_idxs.setdefault(ind, []).append(i)

        for ind, idxs in ind_idxs.items():
            ind_total = sum(int_w[i] for i in idxs)
            if ind_total > MAX_INDUSTRY:
                excess = ind_total - MAX_INDUSTRY
                # Trim the industry members proportionally (highest first)
                sorted_idxs = sorted(idxs, key=lambda i: int_w[i], reverse=True)
                for i in sorted_idxs:
                    if excess <= 0:
                        break
                    cut = min(int_w[i] - 1, excess)
                    if cut > 0:
                        int_w[i] -= cut
                        excess -= cut
                changed = True

        if not changed:
            break

    allocations = {
        candidates[i]['stock_code']: int_w[i]
        for i in range(n)
        if int_w[i] > 0
    }
    cash_pct = max(0, 100 - sum(allocations.values()))

    # Step 5: Validate
    violations = []
    count = len(allocations)
    if count < 8:
        violations.append(f'Stock count {count} < 8 (insufficient eligible stocks)')
    if count > 12:
        violations.append(f'Stock count {count} > 12')

    for code, pct in allocations.items():
        if pct > 25:
            violations.append(f'{code} position {pct}% > 25%')

    ind_totals: Dict[str, int] = {}
    for s in candidates:
        code = s['stock_code']
        if code in allocations:
            ind = s.get('industry', '')
            ind_totals[ind] = ind_totals.get(ind, 0) + allocations[code]
    for ind, total in ind_totals.items():
        if total > 40:
            violations.append(f'Industry {ind}: {total}% > 40%')

    has_yy = any(s.get('tier') == 'Far Ahead' for s in candidates)
    if has_yy:
        yy_total = sum(
            allocations.get(s['stock_code'], 0)
            for s in candidates if s.get('tier') == 'Far Ahead'
        )
        if yy_total < 60:
            violations.append(f'Far Ahead tier {yy_total}% < 60%')

    leading_total = sum(
        allocations.get(s['stock_code'], 0)
        for s in candidates if s.get('tier') == 'Leading'
    )
    if leading_total > 30:
        violations.append(f'Leading tier {leading_total}% > 30%')

    return {
        'allocations': allocations,
        'cash_pct': cash_pct,
        'constraints_met': len(violations) == 0,
        'violations': violations,
    }


# ---------------------------------------------------------------------------
# High-level orchestration
# ---------------------------------------------------------------------------

def get_enriched_stocks(user_id: int) -> List[dict]:
    """
    Returns stocks with all computed fields appended:
    tgt_26, tgt_27, return_27, growth_27, market_factors, adj_return, suggested_pct.
    """
    stocks = list_stocks(user_id)
    latest_run = get_latest_optimizer_run(user_id)
    suggested: Dict[str, float] = latest_run['result'] if latest_run else {}

    enriched = []
    for s in stocks:
        mktcap = s.get('market_cap')
        s['tgt_26'] = round(calc_tgt(s, '26'), 2)
        s['tgt_27'] = round(calc_tgt(s, '27'), 2)
        r27 = calc_return_27(s, mktcap)
        s['return_27'] = round(r27, 4) if r27 is not None else None
        g27 = calc_growth_27(s)
        s['growth_27'] = round(g27, 2) if g27 is not None else None
        factors = calc_market_factors(s, mktcap, stocks)
        s['market_factors'] = factors
        adj = calc_adj_return(r27, factors)
        s['adj_return'] = round(adj, 4) if adj is not None else None
        s['suggested_pct'] = suggested.get(s['stock_code'])
        enriched.append(s)

    return enriched


def get_portfolio_overview(user_id: int) -> dict:
    """Compute overview metrics for Tab 1."""
    stocks = get_enriched_stocks(user_id)
    latest_run = get_latest_optimizer_run(user_id)

    total_pos = sum(float(s.get('position_pct') or 0) for s in stocks)

    weighted_return = None
    weighted_pe = None
    if total_pos > 0:
        wr_num = sum(
            float(s.get('position_pct') or 0) * float(s.get('return_27') or 0)
            for s in stocks if s.get('return_27') is not None
        )
        weighted_return = round(wr_num / total_pos, 4)

        wp_denom = sum(float(s.get('position_pct') or 0) for s in stocks if s.get('pe_27'))
        if wp_denom > 0:
            wp_num = sum(
                float(s.get('position_pct') or 0) * float(s.get('pe_27') or 0)
                for s in stocks if s.get('pe_27')
            )
            weighted_pe = round(wp_num / wp_denom, 2)

    yy_pct = sum(float(s.get('position_pct') or 0) for s in stocks if s.get('tier') == 'Far Ahead')
    leading_pct = sum(float(s.get('position_pct') or 0) for s in stocks if s.get('tier') == 'Leading')

    # Industry breakdown
    ind_map: Dict[str, dict] = {}
    for s in stocks:
        ind = s.get('industry') or 'Other'
        if ind not in ind_map:
            ind_map[ind] = {'industry': ind, 'position_pct': 0.0, 'stock_count': 0}
        ind_map[ind]['position_pct'] += float(s.get('position_pct') or 0)
        ind_map[ind]['stock_count'] += 1
    industry_weights = sorted(ind_map.values(), key=lambda x: x['position_pct'], reverse=True)

    # Bubble chart data (growth vs PE, size=position)
    bubble_data = [
        {
            'stock_code': s['stock_code'],
            'stock_name': s.get('stock_name', ''),
            'industry': s.get('industry') or '',
            'growth_27': s.get('growth_27'),
            'pe_27': float(s.get('pe_27') or 0) if s.get('pe_27') else None,
            'position_pct': float(s.get('position_pct') or 0),
            'return_27': s.get('return_27'),
        }
        for s in stocks
    ]

    return {
        'stock_count': len(stocks),
        'weighted_return_27': weighted_return,
        'weighted_pe_27': weighted_pe,
        'yy_pct': round(yy_pct, 2),
        'leading_pct': round(leading_pct, 2),
        'industry_weights': industry_weights,
        'bubble_data': bubble_data,
        'latest_optimizer_run_id': latest_run['id'] if latest_run else None,
    }


def run_full_optimize(user_id: int) -> dict:
    """
    Run the optimizer on all portfolio stocks, persist result, return full response.
    """
    stocks = get_enriched_stocks(user_id)
    opt_input = [
        {
            'stock_code': s['stock_code'],
            'stock_name': s.get('stock_name', ''),
            'industry': s.get('industry', ''),
            'tier': s.get('tier', ''),
            'status': s.get('status', 'hold'),
            'return_27': s.get('return_27'),
            'adj_return': s.get('adj_return'),
            'research_depth': s.get('research_depth', 80),
            'payout_ratio': float(s.get('payout_ratio') or 0),
            'position_pct': float(s.get('position_pct') or 0),
            'growth_27': s.get('growth_27'),
            'pe_27': float(s.get('pe_27') or 0) if s.get('pe_27') else None,
        }
        for s in stocks
    ]

    opt_result = run_optimizer(opt_input)
    allocations = opt_result['allocations']
    cash_pct = opt_result['cash_pct']

    # Build portfolio metrics
    total_invested = sum(allocations.values())
    stock_map = {s['stock_code']: s for s in stocks}

    yy_total = sum(
        allocations.get(s['stock_code'], 0)
        for s in opt_input if s.get('tier') == 'Far Ahead'
    )
    leading_total = sum(
        allocations.get(s['stock_code'], 0)
        for s in opt_input if s.get('tier') == 'Leading'
    )

    wr = None
    if total_invested > 0:
        wr_num = sum(
            allocations[code] * float(stock_map[code].get('return_27') or 0)
            for code in allocations
            if code in stock_map and stock_map[code].get('return_27') is not None
        )
        wr = round(wr_num / total_invested, 4)

    wp = None
    wp_denom = sum(allocations[c] for c in allocations if stock_map.get(c) and stock_map[c].get('pe_27'))
    if wp_denom > 0:
        wp_num = sum(
            allocations[c] * float(stock_map[c].get('pe_27') or 0)
            for c in allocations
            if stock_map.get(c) and stock_map[c].get('pe_27')
        )
        wp = round(wp_num / wp_denom, 2)

    metrics = {
        'stock_count': len(allocations),
        'weighted_return_27': wr,
        'weighted_pe_27': wp,
        'yy_pct': float(yy_total),
        'leading_pct': float(leading_total),
        'cash_pct': float(cash_pct),
        'constraints_met': opt_result['constraints_met'],
        'constraint_violations': opt_result.get('violations', []),
    }

    run_id = save_optimizer_run(opt_input, allocations, metrics, user_id)

    # Build detail rows
    detail = []
    for code, pct in sorted(allocations.items(), key=lambda x: x[1], reverse=True):
        s_orig = stock_map.get(code) or {}
        mktcap = s_orig.get('market_cap')
        tgt27 = calc_tgt(s_orig, '27')
        val_gap = (tgt27 / mktcap - 1) if (mktcap and mktcap > 0 and tgt27 > 0) else None
        payout = float(s_orig.get('payout_ratio') or 0)
        p27 = float(s_orig.get('profit_27') or 0)
        div_yield = payout * p27 / mktcap if (mktcap and mktcap > 0) else None
        detail.append({
            'stock_code': code,
            'stock_name': s_orig.get('stock_name', ''),
            'industry': s_orig.get('industry', ''),
            'suggested_pct': pct,
            'return_27': s_orig.get('return_27'),
            'growth_27': s_orig.get('growth_27'),
            'div_yield': round(div_yield, 4) if div_yield is not None else None,
            'valuation_gap': round(val_gap, 4) if val_gap is not None else None,
        })

    return {
        'run_id': run_id,
        'allocations': allocations,
        'metrics': metrics,
        'detail': detail,
        'constraints_met': opt_result['constraints_met'],
    }
