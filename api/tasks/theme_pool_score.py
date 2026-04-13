# -*- coding: utf-8 -*-
"""
Theme Pool daily scoring task

Runs after market close to score all stocks in active theme pools.
Scoring dimensions:
  - RPS (20/60/120/250 day)
  - Technical (MA position, MACD, RSI, volume ratio)
  - Fundamental (PE/PB/ROE percentile)
  - Return tracking (5d/10d/20d/60d from entry price)
"""
import json
import logging
import traceback
from datetime import datetime, date, timedelta

logger = logging.getLogger('myTrader.tasks')

# Default scoring weights
WEIGHTS = {
    'rps': 0.40,
    'tech': 0.40,
    'fundamental': 0.20,
}


def run_theme_pool_score(dry_run: bool = False, env: str = 'online'):
    """
    Score all stocks in active theme pools.
    Called by scheduler adapter or Celery.
    """
    if dry_run:
        logger.info('[DRY-RUN] run_theme_pool_score: would score all active theme pool stocks')
        return

    import os
    import sys
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)

    from config.db import execute_query, execute_update

    # 1. Get all stocks from active themes (using API DB)
    stocks = _get_active_theme_stocks(env)
    if not stocks:
        logger.info('[THEME_POOL_SCORE] no active theme stocks to score')
        return

    logger.info('[THEME_POOL_SCORE] scoring %d stocks across active themes', len(stocks))

    score_date = date.today()
    scored = 0
    errors = 0

    for stock in stocks:
        try:
            score = _calc_score(
                stock_code=stock['stock_code'],
                entry_price=stock['entry_price'],
                entry_date=stock['entry_date'],
                score_date=score_date,
                env=env,
            )
            _save_score(stock['id'], score_date, score, env)
            scored += 1
        except Exception as e:
            logger.error('[THEME_POOL_SCORE] failed %s: %s', stock['stock_code'], str(e))
            errors += 1

    logger.info('[THEME_POOL_SCORE] done: scored=%d errors=%d', scored, errors)


def run_theme_pool_score_for_theme(theme_id: int, dry_run: bool = False, env: str = 'online'):
    """Score all stocks in a specific theme (manual trigger)."""
    if dry_run:
        logger.info('[DRY-RUN] run_theme_pool_score_for_theme: theme=%d', theme_id)
        return

    from config.db import execute_query

    sql = """
        SELECT s.id, s.stock_code, s.entry_price, s.entry_date
        FROM theme_pool_stocks s
        WHERE s.theme_id = %s
    """
    try:
        stocks = list(execute_query(sql, (theme_id,), env=env))
    except Exception as e:
        logger.error('[THEME_POOL_SCORE] failed to load stocks for theme=%d: %s', theme_id, e)
        return

    if not stocks:
        logger.info('[THEME_POOL_SCORE] no stocks in theme=%d', theme_id)
        return

    logger.info('[THEME_POOL_SCORE] manual scoring %d stocks for theme=%d', len(stocks), theme_id)
    score_date = date.today()
    scored = 0
    errors = 0

    for stock in stocks:
        try:
            score = _calc_score(
                stock_code=stock['stock_code'],
                entry_price=stock['entry_price'],
                entry_date=stock['entry_date'],
                score_date=score_date,
                env=env,
            )
            _save_score(stock['id'], score_date, score, env)
            scored += 1
        except Exception as e:
            logger.error('[THEME_POOL_SCORE] failed %s: %s', stock['stock_code'], str(e))
            errors += 1

    logger.info('[THEME_POOL_SCORE] theme=%d done: scored=%d errors=%d', theme_id, scored, errors)


def _get_active_theme_stocks(env: str) -> list:
    """Get all stocks from active themes via sync DB."""
    from config.db import execute_query

    # Query the API database (same DB as users/theme_pools tables)
    sql = """
        SELECT s.id, s.stock_code, s.entry_price, s.entry_date
        FROM theme_pool_stocks s
        JOIN theme_pools t ON t.id = s.theme_id
        WHERE t.status = 'active'
    """
    try:
        rows = list(execute_query(sql, env=env))
        return rows
    except Exception as e:
        logger.error('[THEME_POOL_SCORE] failed to load stocks: %s', e)
        return []


def _calc_score(stock_code: str, entry_price: float, entry_date, score_date: date, env: str) -> dict:
    """Calculate multi-dimensional score for a single stock."""
    result = {}

    # -- RPS scores --
    rps = _get_rps(stock_code, env)
    result['rps_20'] = rps.get('rps_20')
    result['rps_60'] = rps.get('rps_60')
    result['rps_120'] = rps.get('rps_120')
    result['rps_250'] = rps.get('rps_250')

    # -- Technical score --
    tech = _calc_tech_score(stock_code, env)
    result['tech_score'] = tech.get('score')
    result['tech_signals'] = json.dumps(tech.get('signals', []), ensure_ascii=True)

    # -- Fundamental score --
    fund = _calc_fundamental_score(stock_code, env)
    result['fundamental_score'] = fund.get('score')
    result['fundamental_data'] = json.dumps(fund.get('data', {}), ensure_ascii=True)

    # -- Weighted total --
    rps_avg = _safe_avg([result['rps_20'], result['rps_60'], result['rps_120']])
    t = result['tech_score']
    f = result['fundamental_score']
    components = []
    if rps_avg is not None:
        components.append(('rps', rps_avg, WEIGHTS['rps']))
    if t is not None:
        components.append(('tech', t, WEIGHTS['tech']))
    if f is not None:
        components.append(('fundamental', f, WEIGHTS['fundamental']))

    if components:
        total_weight = sum(w for _, _, w in components)
        result['total_score'] = round(sum(s * w for _, s, w in components) / total_weight, 2)
    else:
        result['total_score'] = None

    # -- Return tracking --
    returns = _calc_returns(stock_code, entry_price, entry_date, score_date, env)
    result['return_5d'] = returns.get('return_5d')
    result['return_10d'] = returns.get('return_10d')
    result['return_20d'] = returns.get('return_20d')
    result['return_60d'] = returns.get('return_60d')

    return result


def _get_rps(stock_code: str, env: str) -> dict:
    """Get latest RPS values from trade_stock_rps."""
    from config.db import execute_query

    sql = """
        SELECT rps_20, rps_60, rps_120, rps_250
        FROM trade_stock_rps
        WHERE stock_code = %s
        ORDER BY trade_date DESC LIMIT 1
    """
    try:
        rows = list(execute_query(sql, (stock_code,), env=env))
        if rows:
            return {
                'rps_20': _to_float(rows[0].get('rps_20')),
                'rps_60': _to_float(rows[0].get('rps_60')),
                'rps_120': _to_float(rows[0].get('rps_120')),
                'rps_250': _to_float(rows[0].get('rps_250')),
            }
    except Exception as e:
        logger.warning('[THEME_POOL_SCORE] RPS query failed for %s: %s', stock_code, e)
    return {}


def _calc_tech_score(stock_code: str, env: str) -> dict:
    """Calculate technical score based on MA position, MACD, RSI, volume.

    Uses research_tech_snapshots table which stores pre-computed indicators.
    Falls back to computing from trade_stock_daily if snapshot is missing.
    """
    from config.db import execute_query

    # strip .SH/.SZ suffix for research_tech_snapshots (uses pure code like 000688)
    code_short = stock_code.split('.')[0]

    sql = """
        SELECT tech_score, trend_badge, close,
               ma5, ma20, ma60, ma250,
               macd_dif, macd_dea, macd_hist,
               rsi14, vol_ratio_5d, signals_json
        FROM research_tech_snapshots
        WHERE code = %s
        ORDER BY snap_date DESC LIMIT 1
    """
    try:
        rows = list(execute_query(sql, (code_short,), env=env))
        if rows:
            r = rows[0]
            score = _to_float(r.get('tech_score'))
            if score is not None:
                signals = []
                raw_signals = r.get('signals_json')
                if raw_signals:
                    try:
                        signals = json.loads(raw_signals) if isinstance(raw_signals, str) else raw_signals
                    except (json.JSONDecodeError, TypeError):
                        signals = []

                close = _to_float(r.get('close'))
                ma5 = _to_float(r.get('ma5'))
                ma20 = _to_float(r.get('ma20'))
                ma60 = _to_float(r.get('ma60'))
                ma250 = _to_float(r.get('ma250'))
                macd_dif = _to_float(r.get('macd_dif'))
                macd_dea = _to_float(r.get('macd_dea'))
                rsi14 = _to_float(r.get('rsi14'))
                vol_ratio = _to_float(r.get('vol_ratio_5d'))

                if close and ma5 and close > ma5:
                    signals.append('above_ma5')
                if close and ma20 and close > ma20:
                    signals.append('above_ma20')
                if close and ma60 and close > ma60:
                    signals.append('above_ma60')
                if close and ma250 and close > ma250:
                    signals.append('above_ma250')
                if macd_dif is not None and macd_dea is not None and macd_dif > macd_dea:
                    signals.append('macd_bullish')
                if rsi14 is not None and 40 <= rsi14 <= 70:
                    signals.append('rsi_healthy')
                elif rsi14 is not None and rsi14 > 80:
                    signals.append('rsi_overbought')
                elif rsi14 is not None and rsi14 < 30:
                    signals.append('rsi_oversold')
                if vol_ratio is not None and 1.2 <= vol_ratio <= 3.0:
                    signals.append('volume_expansion')

                signals = list(dict.fromkeys(signals))
                return {'score': round(score, 1), 'signals': signals}
    except Exception as e:
        logger.warning('[THEME_POOL_SCORE] tech snapshot lookup failed for %s: %s', stock_code, e)

    # Fallback: compute from trade_stock_daily
    return _calc_tech_score_from_daily(stock_code, env)


def _calc_tech_score_from_daily(stock_code: str, env: str) -> dict:
    """Compute technical score directly from daily OHLCV data."""
    from config.db import execute_query

    try:
        rows = list(execute_query(
            "SELECT trade_date, close_price, volume "
            "FROM trade_stock_daily "
            "WHERE stock_code = %s "
            "ORDER BY trade_date DESC LIMIT 260",
            (stock_code,), env=env,
        ))
        if not rows:
            return {'score': None, 'signals': []}

        # Reverse to chronological order for rolling calculations
        rows.reverse()
        closes = [_to_float(r['close_price']) for r in rows]
        volumes = [_to_float(r['volume']) for r in rows]
        close = closes[-1]

        if not close:
            return {'score': None, 'signals': []}

        score = 50.0
        signals = []

        # MA calculations
        def ma(data, window):
            if len(data) < window:
                return None
            return sum(data[-window:]) / window

        ma5 = ma(closes, 5)
        ma20 = ma(closes, 20)
        ma60 = ma(closes, 60)
        ma250 = ma(closes, 250)

        if ma5 and close > ma5:
            score += 5
            signals.append('above_ma5')
        if ma20 and close > ma20:
            score += 10
            signals.append('above_ma20')
        if ma60 and close > ma60:
            score += 10
            signals.append('above_ma60')
        if ma250 and close > ma250:
            score += 5
            signals.append('above_ma250')

        # MACD (12, 26, 9)
        def ema(data, span):
            if len(data) < span:
                return None
            k = 2 / (span + 1)
            val = data[0]
            for x in data[1:]:
                val = x * k + val * (1 - k)
            return val

        ema12 = ema(closes, 12)
        ema26 = ema(closes, 26)
        if ema12 is not None and ema26 is not None:
            dif = ema12 - ema26
            # Approximate DEA from recent DIF values
            dif_series = []
            for i in range(26, len(closes) + 1):
                e12 = ema(closes[:i], 12)
                e26 = ema(closes[:i], 26)
                if e12 is not None and e26 is not None:
                    dif_series.append(e12 - e26)
            if len(dif_series) >= 9:
                dea = ema(dif_series, 9)
                if dea is not None and dif > dea:
                    score += 10
                    signals.append('macd_bullish')
                elif dea is not None:
                    score -= 5

        # RSI(14)
        if len(closes) > 14:
            deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
            recent = deltas[-14:]
            gains = [d for d in recent if d > 0]
            losses = [-d for d in recent if d < 0]
            avg_gain = sum(gains) / 14 if gains else 0
            avg_loss = sum(losses) / 14 if losses else 0
            if avg_loss > 0:
                rs = avg_gain / avg_loss
                rsi = 100 - 100 / (1 + rs)
            else:
                rsi = 100
            if 40 <= rsi <= 70:
                score += 5
                signals.append('rsi_healthy')
            elif rsi > 80:
                score -= 10
                signals.append('rsi_overbought')
            elif rsi < 30:
                score -= 5
                signals.append('rsi_oversold')

        # Volume ratio (5d avg)
        if len(volumes) >= 6:
            avg_vol_5 = sum(volumes[-6:-1]) / 5
            if avg_vol_5 > 0:
                vol_ratio = volumes[-1] / avg_vol_5
                if 1.2 <= vol_ratio <= 3.0:
                    score += 5
                    signals.append('volume_expansion')

        score = max(0, min(100, score))
        return {'score': round(score, 1), 'signals': signals}

    except Exception as e:
        logger.warning('[THEME_POOL_SCORE] tech score from daily failed for %s: %s', stock_code, e)
        return {'score': None, 'signals': []}


def _calc_fundamental_score(stock_code: str, env: str) -> dict:
    """Calculate fundamental score from financial data.

    Uses trade_stock_extended_factor (roe_ttm, net_profit_growth, revenue_growth)
    and trade_stock_valuation_factor (pe_ttm, pb).
    """
    from config.db import execute_query

    try:
        # Valuation: pe_ttm, pb
        val_rows = list(execute_query(
            "SELECT pe_ttm, pb FROM trade_stock_valuation_factor "
            "WHERE stock_code = %s ORDER BY calc_date DESC LIMIT 1",
            (stock_code,), env=env,
        ))
        pe = _to_float(val_rows[0].get('pe_ttm')) if val_rows else None
        pb = _to_float(val_rows[0].get('pb')) if val_rows else None

        # Quality: roe_ttm, net_profit_growth, revenue_growth
        ext_rows = list(execute_query(
            "SELECT roe_ttm, gross_margin, net_profit_growth, revenue_growth "
            "FROM trade_stock_extended_factor "
            "WHERE stock_code = %s ORDER BY calc_date DESC LIMIT 1",
            (stock_code,), env=env,
        ))
        roe = _to_float(ext_rows[0].get('roe_ttm')) if ext_rows else None
        profit_growth = _to_float(ext_rows[0].get('net_profit_growth')) if ext_rows else None
        rev_growth = _to_float(ext_rows[0].get('revenue_growth')) if ext_rows else None

        data = {
            'pe_ttm': pe,
            'pb': pb,
            'roe': roe,
            'revenue_growth': rev_growth,
            'net_profit_growth': profit_growth,
        }

        if not any(v is not None for v in [pe, pb, roe, profit_growth, rev_growth]):
            return {'score': None, 'data': data}

        score = 50.0

        # ROE scoring
        if roe is not None:
            if roe >= 20:
                score += 20
            elif roe >= 15:
                score += 15
            elif roe >= 10:
                score += 10
            elif roe >= 5:
                score += 5
            elif roe < 0:
                score -= 15

        # PE scoring (lower is better, but negative means loss)
        if pe is not None:
            if pe < 0:
                score -= 15
            elif pe <= 15:
                score += 15
            elif pe <= 30:
                score += 10
            elif pe <= 50:
                score += 5
            elif pe > 100:
                score -= 10

        # Growth scoring (profit_growth is decimal, e.g. 0.5 = 50%)
        if profit_growth is not None:
            pct = profit_growth * 100
            if pct > 50:
                score += 15
            elif pct > 20:
                score += 10
            elif pct > 0:
                score += 5
            elif pct < -20:
                score -= 10

        score = max(0, min(100, score))
        return {'score': round(score, 1), 'data': data}

    except Exception as e:
        logger.warning('[THEME_POOL_SCORE] fundamental score failed for %s: %s', stock_code, e)
        return {'score': None, 'data': {}}


def _calc_returns(stock_code: str, entry_price: float, entry_date, score_date: date, env: str) -> dict:
    """Calculate returns from entry price at different windows."""
    from config.db import execute_query

    if not entry_price or entry_price <= 0:
        return {}

    result = {}

    # Get recent close prices ordered by date desc
    sql = """
        SELECT trade_date, close_price
        FROM trade_stock_daily
        WHERE stock_code = %s
        ORDER BY trade_date DESC LIMIT 60
    """
    try:
        rows = list(execute_query(sql, (stock_code,), env=env))
        if not rows:
            return {}

        latest_close = _to_float(rows[0].get('close_price'))
        if not latest_close:
            return {}

        # Calculate return from entry_price to price at different windows
        # return_5d = (price 5 days ago - entry_price) / entry_price * 100
        for window, key in [(5, 'return_5d'), (10, 'return_10d'), (20, 'return_20d'), (60, 'return_60d')]:
            if len(rows) >= window:
                past_close = _to_float(rows[min(window - 1, len(rows) - 1)].get('close_price'))
                if past_close and past_close > 0:
                    result[key] = round((past_close - entry_price) / entry_price * 100, 2)
                else:
                    result[key] = None
            else:
                # Not enough history, use latest close
                result[key] = round((latest_close - entry_price) / entry_price * 100, 2)

    except Exception as e:
        logger.warning('[THEME_POOL_SCORE] return calc failed for %s: %s', stock_code, e)

    return result


def _save_score(theme_stock_id: int, score_date: date, score: dict, env: str):
    """Save or update score record."""
    from config.db import execute_update

    sql = """
        INSERT INTO theme_pool_scores
            (theme_stock_id, score_date, rps_20, rps_60, rps_120, rps_250,
             tech_score, tech_signals, fundamental_score, fundamental_data,
             total_score, return_5d, return_10d, return_20d, return_60d, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        ON DUPLICATE KEY UPDATE
            rps_20 = VALUES(rps_20),
            rps_60 = VALUES(rps_60),
            rps_120 = VALUES(rps_120),
            rps_250 = VALUES(rps_250),
            tech_score = VALUES(tech_score),
            tech_signals = VALUES(tech_signals),
            fundamental_score = VALUES(fundamental_score),
            fundamental_data = VALUES(fundamental_data),
            total_score = VALUES(total_score),
            return_5d = VALUES(return_5d),
            return_10d = VALUES(return_10d),
            return_20d = VALUES(return_20d),
            return_60d = VALUES(return_60d)
    """
    params = (
        theme_stock_id, score_date,
        score.get('rps_20'), score.get('rps_60'), score.get('rps_120'), score.get('rps_250'),
        score.get('tech_score'), score.get('tech_signals'),
        score.get('fundamental_score'), score.get('fundamental_data'),
        score.get('total_score'),
        score.get('return_5d'), score.get('return_10d'),
        score.get('return_20d'), score.get('return_60d'),
    )
    execute_update(sql, params, env=env)


# ------------------------------------------------------------------
# Utils
# ------------------------------------------------------------------

def _to_float(val) -> float:
    """Safely convert a value to float."""
    if val is None:
        return None
    try:
        from decimal import Decimal
        if isinstance(val, Decimal):
            return float(val)
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_avg(values: list) -> float:
    """Average of non-None values."""
    valid = [v for v in values if v is not None]
    if not valid:
        return None
    return sum(valid) / len(valid)
