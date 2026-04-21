# -*- coding: utf-8 -*-
"""
Market Dashboard Calculator - aggregation layer.

Integrates data from:
  - data_analyst.market_overview.calculator  (8 signal groups)
  - data_analyst.sentiment                   (fear index, events)
  - data_analyst.market_monitor              (SVD market state)
  - macro_data table                         (new indicators)
  - trade_stock_daily table                  (turnover, advance/decline)

Outputs a unified 6-section dashboard + signal change log.
No emoji - plain text labels only.
"""
import logging
import os
import sys
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from config.db import execute_query
from . import config as C

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _signal(value: float, thresholds: list, labels: list) -> str:
    """Map a numeric value to a label based on ascending thresholds."""
    for i, t in enumerate(thresholds):
        if value < t:
            return labels[i]
    return labels[-1]


def _load_macro(indicator: str, days: int = 500) -> pd.Series:
    """Load a single indicator from macro_data as float Series indexed by date."""
    cutoff = (date.today() - timedelta(days=days)).strftime('%Y-%m-%d')
    rows = execute_query(
        "SELECT date, value FROM macro_data WHERE indicator=%s AND date >= %s ORDER BY date",
        (indicator, cutoff),
    )
    if not rows:
        return pd.Series(dtype=float)
    data = {}
    for r in rows:
        if r['value'] is not None:
            data[r['date']] = float(r['value'])
    if not data:
        return pd.Series(dtype=float)
    s = pd.Series(data)
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _safe_round(val, decimals=2):
    """Safely round a value that might be None or NaN."""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
        return round(float(val), decimals)
    except (TypeError, ValueError):
        return None


def _pct_change_str(cur, prev):
    """Return percentage change string like '+5.2%' or '-3.1%'."""
    if cur is None or prev is None or prev == 0:
        return None
    change = (cur - prev) / prev * 100
    sign = '+' if change >= 0 else ''
    return f"{sign}{change:.1f}%"


# ---------------------------------------------------------------------------
# Section 1: Market Temperature
# ---------------------------------------------------------------------------

def calc_temperature() -> dict:
    """
    Market temperature: how hot or cold is the overall market?

    Indicators:
    - Total market volume (two exchanges)
    - Volume / MA20 ratio
    - Average turnover rate percentile
    - Advance / decline count
    - Limit up / limit down count
    - Margin balance 5-day change rate
    """
    try:
        result = {'available': True, 'indicators': {}}

        # 1) Market volume
        vol_series = _load_macro('market_volume', days=60)
        volume_anomaly = False
        if not vol_series.empty:
            # Filter outliers: remove data points < 30% of rolling median (corrupted data)
            rolling_median = vol_series.rolling(window=5, min_periods=2, center=True).median()
            outlier_mask = vol_series < (rolling_median * 0.3)
            if outlier_mask.any():
                outlier_dates = vol_series.index[outlier_mask].strftime('%Y-%m-%d').tolist()
                logger.warning("[ANOMALY] Filtering %d volume outlier(s): %s", outlier_mask.sum(), outlier_dates)
                vol_series = vol_series[~outlier_mask]

            if vol_series.empty:
                result['indicators']['volume'] = {'value': None}
                result['indicators']['volume_ratio_ma20'] = {'value': None, 'signal': 'unknown'}
                result['volume_series'] = []
            else:
                cur_vol = float(vol_series.iloc[-1])
                prev_vol = float(vol_series.iloc[-2]) if len(vol_series) >= 2 else None
                ma20 = float(vol_series.tail(20).mean()) if len(vol_series) >= 5 else None
                vol_ratio = cur_vol / ma20 if ma20 and ma20 > 0 else None

                # Final anomaly check on current value
                if vol_ratio is not None and vol_ratio < 0.1:
                    logger.warning(
                        "[ANOMALY] market_volume %.0f is <10%% of MA20 %.0f (ratio=%.4f), marking anomalous",
                        cur_vol, ma20, vol_ratio,
                    )
                    volume_anomaly = True
                    result['indicators']['volume'] = {
                        'value': _safe_round(cur_vol / 1e8, 0),
                        'unit': 'yi',
                        'anomaly': '[ANOMALY: volume far below MA20, data likely corrupt]',
                    }
                    result['indicators']['volume_ratio_ma20'] = {
                        'value': None,
                        'signal': 'anomaly',
                        'anomaly': '[ANOMALY]',
                    }
                else:
                    result['indicators']['volume'] = {
                        'value': _safe_round(cur_vol / 1e8, 0),  # convert to yi
                        'unit': 'yi',
                        'change': _pct_change_str(cur_vol, prev_vol),
                    }
                    result['indicators']['volume_ratio_ma20'] = {
                        'value': _safe_round(vol_ratio, 2),
                        'signal': _signal(vol_ratio or 1.0, C.VOLUME_RATIO_THRESHOLDS, C.VOLUME_RATIO_LEVELS),
                    }
                # Series for sparkline: last 20 days volume (outliers already removed)
                result['volume_series'] = [
                    {'date': d.strftime('%Y-%m-%d'), 'value': _safe_round(float(v) / 1e8, 0)}
                    for d, v in vol_series.tail(20).items()
                ]
        else:
            result['indicators']['volume'] = {'value': None}
            result['indicators']['volume_ratio_ma20'] = {'value': None, 'signal': 'unknown'}
            result['volume_series'] = []

        # 2) Turnover rate - compute from macro_data market_volume instead of
        #    trade_stock_daily (which is too large for real-time query)
        if not vol_series.empty and len(vol_series) >= 20 and not volume_anomaly:
            window = vol_series.tail(252) if len(vol_series) >= 252 else vol_series
            cur_vol_val = float(vol_series.iloc[-1])
            pct_rank = round(float((window < cur_vol_val).mean() * 100), 1) if len(window) > 10 else None
            result['indicators']['turnover_pct_rank'] = {
                'value': pct_rank,
                'signal': _signal(
                    pct_rank or 50,
                    C.TURNOVER_PCT_THRESHOLDS,
                    C.TURNOVER_PCT_LEVELS,
                ),
            }
        else:
            result['indicators']['turnover_pct_rank'] = {'value': None, 'signal': 'unknown'}

        # 3) Advance / decline count
        adv = _load_macro('advance_count', days=30)
        dec = _load_macro('decline_count', days=30)
        if not adv.empty and not dec.empty:
            cur_adv = int(float(adv.iloc[-1]))
            cur_dec = int(float(dec.iloc[-1]))
            ratio = cur_adv / cur_dec if cur_dec > 0 else 999
            result['indicators']['advance_decline'] = {
                'advance': cur_adv,
                'decline': cur_dec,
                'ratio': _safe_round(ratio, 2),
                'signal': _signal(ratio, C.ADV_DEC_RATIO_THRESHOLDS, C.ADV_DEC_LEVELS),
            }
        else:
            result['indicators']['advance_decline'] = {'advance': None, 'decline': None, 'ratio': None, 'signal': 'unknown'}

        # 4) Limit up / limit down
        lu = _load_macro('limit_up_count', days=30)
        ld = _load_macro('limit_down_count', days=30)
        if not lu.empty and not ld.empty:
            result['indicators']['limit_up_down'] = {
                'up': int(float(lu.iloc[-1])),
                'down': int(float(ld.iloc[-1])),
            }
        else:
            result['indicators']['limit_up_down'] = {'up': None, 'down': None}

        # 5) Margin balance 5-day change
        margin = _load_macro('margin_balance', days=30)
        if len(margin) >= 6:
            cur_margin = float(margin.iloc[-1])
            prev_margin = float(margin.iloc[-6])  # ~5 trading days ago
            change_pct = (cur_margin - prev_margin) / prev_margin * 100 if prev_margin > 0 else 0
            result['indicators']['margin_change_5d'] = {
                'value': _safe_round(change_pct, 2),
                'unit': '%',
                'signal': _signal(change_pct, C.MARGIN_CHANGE_THRESHOLDS, C.MARGIN_CHANGE_LEVELS),
                'balance': _safe_round(cur_margin / 1e8, 0),
            }
        else:
            result['indicators']['margin_change_5d'] = {'value': None, 'signal': 'unknown'}

        # Composite temperature score (0-100)
        score = _calc_temperature_score(result['indicators'])
        level = _signal(score, C.TEMPERATURE_THRESHOLDS, C.TEMPERATURE_LEVELS)
        result['score'] = score
        result['level'] = level
        result['level_label'] = C.TEMPERATURE_LABELS.get(level, level)

        return result
    except Exception as e:
        logger.error("calc_temperature failed: %s", e)
        return {'available': False, 'error': str(e)}


def _calc_temperature_score(indicators: dict) -> int:
    """Composite temperature score 0-100 from sub-indicators."""
    score = 50  # neutral baseline
    parts = 0

    # Volume ratio contribution: -25 to +25
    vr = indicators.get('volume_ratio_ma20', {}).get('value')
    if vr is not None:
        # 0.7 -> -25, 1.0 -> 0, 1.5 -> +25
        contribution = max(-25, min(25, (vr - 1.0) * 50))
        score += contribution
        parts += 1

    # Turnover percentile contribution: -25 to +25
    tp = indicators.get('turnover_pct_rank', {}).get('value')
    if tp is not None:
        contribution = (tp - 50) * 0.5  # 0% -> -25, 100% -> +25
        score += contribution
        parts += 1

    # Advance/decline ratio contribution: -15 to +15
    adr = indicators.get('advance_decline', {}).get('ratio')
    if adr is not None:
        contribution = max(-15, min(15, (adr - 1.0) * 15))
        score += contribution
        parts += 1

    # Margin change contribution: -10 to +10
    mc = indicators.get('margin_change_5d', {}).get('value')
    if mc is not None:
        contribution = max(-10, min(10, mc * 10))
        score += contribution
        parts += 1

    return max(0, min(100, int(score)))


# ---------------------------------------------------------------------------
# Section 2: Trend & Direction
# ---------------------------------------------------------------------------

def calc_trend() -> dict:
    """
    Trend direction: is the market trending up, consolidating, or trending down?

    Indicators:
    - Major index daily returns
    - Index vs MA positions
    - Moving average alignment
    - MACD weekly status (for CSI300)
    - ADX trend strength
    - SVD market structure
    """
    try:
        result = {'available': True, 'indices': {}, 'indicators': {}}

        # 1) Index daily returns
        for idx_cfg in C.INDEX_CONFIG:
            s = _load_macro(idx_cfg['key'], days=500)
            if len(s) >= 2:
                cur = float(s.iloc[-1])
                prev = float(s.iloc[-2])
                change_pct = (cur - prev) / prev * 100
                result['indices'][idx_cfg['key']] = {
                    'name': idx_cfg['name'],
                    'close': _safe_round(cur, 2),
                    'change_pct': _safe_round(change_pct, 2),
                }
            else:
                result['indices'][idx_cfg['key']] = {
                    'name': idx_cfg['name'],
                    'close': None,
                    'change_pct': None,
                }

        # 2) MA position and alignment for CSI300
        csi300 = _load_macro('idx_csi300', days=500)
        if len(csi300) >= 60:
            cur_price = float(csi300.iloc[-1])
            ma5 = float(csi300.tail(5).mean())
            ma20 = float(csi300.tail(20).mean())
            ma60 = float(csi300.tail(60).mean())
            ma250 = float(csi300.tail(250).mean()) if len(csi300) >= 250 else None

            above = []
            below = []
            for name, val in [('MA5', ma5), ('MA20', ma20), ('MA60', ma60), ('MA250', ma250)]:
                if val is not None and cur_price > val:
                    above.append(name)
                elif val is not None:
                    below.append(name)

            result['indicators']['ma_position'] = {
                'above': above,
                'below': below,
            }

            # MA alignment: bullish (5>20>60), bearish (5<20<60), tangled
            if ma5 > ma20 > ma60:
                alignment = 'bullish'
            elif ma5 < ma20 < ma60:
                alignment = 'bearish'
            else:
                alignment = 'tangled'
            result['indicators']['ma_alignment'] = alignment

            # 3) MACD weekly (approximate: use 5-day resampled data)
            macd_result = _calc_weekly_macd(csi300)
            result['indicators']['macd_weekly'] = macd_result

            # 4) ADX (simplified using DI+/DI- from daily data)
            adx_result = _calc_adx(csi300)
            result['indicators']['adx'] = adx_result

            # Sparkline: 60-day CSI300 + MA20 + MA60
            series_tail = csi300.tail(60)
            ma20_series = csi300.rolling(20).mean().tail(60)
            ma60_series = csi300.rolling(60).mean().tail(60)
            result['trend_series'] = [
                {
                    'date': d.strftime('%Y-%m-%d'),
                    'close': _safe_round(float(series_tail.loc[d]), 2),
                    'ma20': _safe_round(float(ma20_series.loc[d]), 2) if d in ma20_series.index and not pd.isna(ma20_series.loc[d]) else None,
                    'ma60': _safe_round(float(ma60_series.loc[d]), 2) if d in ma60_series.index and not pd.isna(ma60_series.loc[d]) else None,
                }
                for d in series_tail.index
            ]
        else:
            result['indicators']['ma_position'] = {'above': [], 'below': []}
            result['indicators']['ma_alignment'] = 'unknown'
            result['indicators']['macd_weekly'] = {'status': 'unknown'}
            result['indicators']['adx'] = {'value': None, 'signal': 'unknown'}
            result['trend_series'] = []

        # 5) SVD market structure
        svd_data = _get_latest_svd()
        result['indicators']['svd'] = svd_data

        # Composite trend level
        level = _calc_trend_level(result)
        result['level'] = level
        result['level_label'] = C.TREND_LABELS.get(level, level)

        return result
    except Exception as e:
        logger.error("calc_trend failed: %s", e)
        return {'available': False, 'error': str(e)}


def _calc_weekly_macd(daily_series: pd.Series) -> dict:
    """Calculate MACD on weekly-resampled data."""
    try:
        weekly = daily_series.resample('W-FRI').last().dropna()
        if len(weekly) < 35:
            return {'status': 'unknown'}

        ema12 = weekly.ewm(span=12, adjust=False).mean()
        ema26 = weekly.ewm(span=26, adjust=False).mean()
        dif = ema12 - ema26
        dea = dif.ewm(span=9, adjust=False).mean()
        hist = (dif - dea) * 2

        cur_dif = float(dif.iloc[-1])
        cur_dea = float(dea.iloc[-1])
        cur_hist = float(hist.iloc[-1])
        prev_hist = float(hist.iloc[-2]) if len(hist) >= 2 else 0

        # Golden cross / dead cross detection (DIF vs DEA)
        if len(dif) >= 2:
            prev_dif = float(dif.iloc[-2])
            prev_dea = float(dea.iloc[-2])
            if prev_dif <= prev_dea and cur_dif > cur_dea:
                status = 'golden_cross'
            elif prev_dif >= prev_dea and cur_dif < cur_dea:
                status = 'dead_cross'
            elif cur_dif > cur_dea:
                # DIF above DEA (bullish) — further distinguish zero axis
                status = 'above_zero' if cur_dif > 0 else 'dif_above_dea'
            else:
                # DIF below DEA (bearish) — further distinguish zero axis
                status = 'below_zero' if cur_dif < 0 else 'dif_below_dea'
        else:
            status = 'above_zero' if cur_dif > 0 else 'below_zero'

        # Histogram direction
        if cur_hist > 0:
            histogram = 'expanding' if cur_hist > prev_hist else 'contracting'
        else:
            histogram = 'expanding' if cur_hist < prev_hist else 'contracting'

        return {
            'status': status,
            'histogram': histogram,
            'dif': _safe_round(cur_dif, 2),
            'dea': _safe_round(cur_dea, 2),
            'hist': _safe_round(cur_hist, 2),
        }
    except Exception as e:
        logger.warning("_calc_weekly_macd failed: %s", e)
        return {'status': 'unknown'}


def _calc_adx(daily_series: pd.Series, period: int = 14) -> dict:
    """Simplified ADX calculation from price series."""
    try:
        if len(daily_series) < period * 3:
            return {'value': None, 'signal': 'unknown'}

        # Use price changes as proxy for true range (we only have close prices)
        diff = daily_series.diff()
        pos_dm = diff.clip(lower=0)
        neg_dm = (-diff).clip(lower=0)

        tr = daily_series.diff().abs()  # simplified true range
        tr = tr.replace(0, 0.001)  # avoid division by zero

        atr = tr.rolling(period).mean()
        pos_di = 100 * pos_dm.rolling(period).mean() / atr
        neg_di = 100 * neg_dm.rolling(period).mean() / atr
        dx = 100 * (pos_di - neg_di).abs() / (pos_di + neg_di).replace(0, 0.001)
        adx = dx.rolling(period).mean()

        cur_adx = float(adx.iloc[-1]) if not pd.isna(adx.iloc[-1]) else None
        if cur_adx is not None:
            signal = _signal(cur_adx, C.ADX_THRESHOLDS, C.ADX_LEVELS)
        else:
            signal = 'unknown'

        return {
            'value': _safe_round(cur_adx, 1),
            'signal': signal,
        }
    except Exception as e:
        logger.warning("_calc_adx failed: %s", e)
        return {'value': None, 'signal': 'unknown'}


def _get_latest_svd() -> dict:
    """Get the latest SVD market state from trade_svd_market_state."""
    try:
        rows = execute_query(
            "SELECT calc_date, market_state, top1_var_ratio, is_mutation "
            "FROM trade_svd_market_state "
            "WHERE universe_type=%s AND window_size=%s "
            "ORDER BY calc_date DESC LIMIT 1",
            ('全A', 20),
        )
        if rows:
            r = rows[0]
            state_labels = {
                'beta_dominant': '齐涨齐跌',
                'sector_rotation': '板块分化',
                'stock_picking': '个股行情',
            }
            return {
                'state': r['market_state'],
                'state_label': state_labels.get(r['market_state'], r['market_state']),
                'top1_ratio': _safe_round(r['top1_var_ratio'], 1),
                'is_mutation': bool(r.get('is_mutation', False)),
                'date': r['calc_date'].strftime('%Y-%m-%d') if hasattr(r['calc_date'], 'strftime') else str(r['calc_date']),
            }
        return {'state': 'unknown', 'state_label': '未知'}
    except Exception as e:
        logger.warning("_get_latest_svd failed: %s", e)
        return {'state': 'unknown', 'state_label': '未知'}


def _calc_trend_level(trend_data: dict) -> str:
    """Composite trend level from sub-indicators."""
    direction_score = 0

    # MA alignment: +15 bullish, -15 bearish, 0 tangled
    alignment = trend_data.get('indicators', {}).get('ma_alignment', 'tangled')
    if alignment == 'bullish':
        direction_score += 15
    elif alignment == 'bearish':
        direction_score -= 15

    # MA position: +5 per above, -5 per below (for MA20/MA60)
    ma_pos = trend_data.get('indicators', {}).get('ma_position', {})
    above = ma_pos.get('above', [])
    below = ma_pos.get('below', [])
    for ma in ['MA20', 'MA60']:
        if ma in above:
            direction_score += 5
        elif ma in below:
            direction_score -= 5

    # MACD weekly: score based on DIF/DEA relationship and zero axis
    macd = trend_data.get('indicators', {}).get('macd_weekly', {})
    macd_status = macd.get('status', 'unknown')
    if macd_status == 'golden_cross':
        direction_score += 10
    elif macd_status == 'above_zero':
        direction_score += 10
    elif macd_status == 'dif_above_dea':
        direction_score += 5  # DIF>DEA but both below zero: recovering
    elif macd_status == 'dif_below_dea':
        direction_score -= 5  # DIF<DEA but both above zero: weakening
    elif macd_status == 'dead_cross':
        direction_score -= 10
    elif macd_status == 'below_zero':
        direction_score -= 10

    # Index daily returns: average across tracked indices
    indices = trend_data.get('indices', {})
    changes = [v.get('change_pct', 0) or 0 for v in indices.values()]
    if changes:
        avg_change = sum(changes) / len(changes)
        direction_score += max(-10, min(10, avg_change * 5))

    # ADX for confidence
    adx = trend_data.get('indicators', {}).get('adx', {}).get('value')
    if adx is not None and adx > 0:
        confidence = max(0.4, min(1.0, adx / 30))
    else:
        confidence = 0.5

    final_score = direction_score * confidence

    if final_score >= 20:
        return 'strong_up'
    elif final_score >= 8:
        return 'mild_up'
    elif final_score <= -20:
        return 'panic_drop'
    elif final_score <= -8:
        return 'weak_down'
    return 'consolidating'


# ---------------------------------------------------------------------------
# Section 3: Sentiment / Fear-Greed
# ---------------------------------------------------------------------------

def calc_sentiment() -> dict:
    """
    Market sentiment: fear or greed?

    Integrates:
    - QVIX (from macro_pulse)
    - Northbound flow (from macro_pulse)
    - VIX (from fear_index service)
    - Advance/decline based sentiment
    """
    try:
        result = {'available': True, 'indicators': {}}

        # 1) QVIX
        qvix_series = _load_macro('qvix', days=45)
        if not qvix_series.empty:
            cur_qvix = float(qvix_series.iloc[-1])
            result['indicators']['qvix'] = {
                'value': _safe_round(cur_qvix, 2),
                'signal': _signal(cur_qvix, C.QVIX_THRESHOLDS, C.QVIX_LEVELS),
            }
        else:
            result['indicators']['qvix'] = {'value': None, 'signal': 'unknown'}

        # 2) Northbound flow
        north_rows = execute_query(
            "SELECT date, value FROM macro_data WHERE indicator=%s "
            "AND value IS NOT NULL ORDER BY date DESC LIMIT 5",
            ('north_flow',),
        )
        if north_rows:
            today_flow = float(north_rows[0]['value']) if north_rows[0]['value'] is not None else None
            sum_5d = sum(float(r['value']) for r in north_rows if r['value'] is not None)
            result['indicators']['north_flow'] = {
                'today': _safe_round(today_flow, 2),
                'sum_5d': _safe_round(sum_5d, 2),
                'signal': 'inflow' if (sum_5d or 0) > 0 else 'outflow',
            }
        else:
            result['indicators']['north_flow'] = {'today': None, 'sum_5d': None, 'signal': 'unknown'}

        # 3) VIX (from trade_fear_index)
        try:
            fear_rows = execute_query(
                "SELECT trade_date, vix, fear_greed_score, market_regime, vix_level "
                "FROM trade_fear_index ORDER BY trade_date DESC LIMIT 1"
            )
            if fear_rows:
                r = fear_rows[0]
                result['indicators']['vix'] = {
                    'value': _safe_round(r['vix'], 2),
                    'level': r.get('vix_level', ''),
                    'fear_greed_score': int(r['fear_greed_score']) if r.get('fear_greed_score') is not None else None,
                    'market_regime': r.get('market_regime', ''),
                }
            else:
                result['indicators']['vix'] = {'value': None}
        except Exception as e:
            logger.warning("fear_index query failed: %s", e)
            result['indicators']['vix'] = {'value': None}

        # 4) Margin net buy
        margin_buy = _load_macro('margin_net_buy', days=10)
        if not margin_buy.empty:
            cur_buy = float(margin_buy.iloc[-1])
            sum_5d = float(margin_buy.tail(5).sum()) if len(margin_buy) >= 5 else None
            result['indicators']['margin_net_buy'] = {
                'today': _safe_round(cur_buy / 1e8, 2),
                'sum_5d': _safe_round(sum_5d / 1e8 if sum_5d else None, 2),
                'unit': 'yi',
            }
        else:
            result['indicators']['margin_net_buy'] = {'today': None, 'sum_5d': None}

        # 5) New highs / new lows
        nh = _load_macro('new_high_60d', days=30)
        nl = _load_macro('new_low_60d', days=30)
        if not nh.empty and not nl.empty:
            cur_nh = int(float(nh.iloc[-1]))
            cur_nl = int(float(nl.iloc[-1]))
            # Both=0 is implausible on a normal trading day; treat as missing data
            # and fall back to the most recent non-zero entry
            if cur_nh == 0 and cur_nl == 0 and len(nh) >= 2:
                for i in range(2, min(len(nh) + 1, 6)):
                    fallback_nh = int(float(nh.iloc[-i]))
                    fallback_nl = int(float(nl.iloc[-i])) if len(nl) >= i else 0
                    if fallback_nh > 0 or fallback_nl > 0:
                        cur_nh = fallback_nh
                        cur_nl = fallback_nl
                        break
            result['indicators']['new_high_low'] = {
                'high': cur_nh,
                'low': cur_nl,
                'signal': 'bullish' if cur_nh > cur_nl * 2 else ('bearish' if cur_nl > cur_nh * 2 else 'neutral'),
            }
        else:
            result['indicators']['new_high_low'] = {'high': None, 'low': None, 'signal': 'unknown'}

        # 6) Seal rate (limit-up holding rate)
        seal = _load_macro('seal_rate', days=30)
        if not seal.empty:
            cur_seal = float(seal.iloc[-1])
            result['indicators']['seal_rate'] = {
                'value': _safe_round(cur_seal, 1),
                'unit': '%',
                'signal': _signal(cur_seal, [50, 70], ['hesitant', 'normal', 'chasing']),
            }
        else:
            result['indicators']['seal_rate'] = {'value': None, 'signal': 'unknown'}

        # Composite A-share fear-greed score
        score = _calc_fear_greed_score(result['indicators'])
        level = _signal(score, C.FEAR_GREED_THRESHOLDS, C.FEAR_GREED_LEVELS)
        result['score'] = score
        result['level'] = level
        result['level_label'] = C.FEAR_GREED_LABELS.get(level, level)

        # Sparkline: fear-greed history from trade_fear_index
        try:
            hist_rows = execute_query(
                "SELECT trade_date, fear_greed_score FROM trade_fear_index "
                "ORDER BY trade_date DESC LIMIT 20"
            )
            if hist_rows:
                result['sentiment_series'] = [
                    {'date': r['trade_date'].strftime('%Y-%m-%d') if hasattr(r['trade_date'], 'strftime') else str(r['trade_date']),
                     'value': int(r['fear_greed_score']) if r.get('fear_greed_score') is not None else None}
                    for r in reversed(hist_rows)
                ]
            else:
                result['sentiment_series'] = []
        except Exception:
            result['sentiment_series'] = []

        return result
    except Exception as e:
        logger.error("calc_sentiment failed: %s", e)
        return {'available': False, 'error': str(e)}


def _calc_fear_greed_score(indicators: dict) -> int:
    """Composite A-share fear-greed score (0-100)."""
    score = 50  # neutral baseline

    # QVIX contribution: -15 to +15
    qvix = indicators.get('qvix', {}).get('value')
    if qvix is not None:
        # Low QVIX = greedy (score up), high QVIX = fearful (score down)
        if qvix < 15:
            score += 10
        elif qvix < 20:
            score += 5
        elif qvix > 35:
            score -= 15
        elif qvix > 25:
            score -= 8

    # Northbound 5-day flow: -10 to +10
    north_5d = indicators.get('north_flow', {}).get('sum_5d')
    if north_5d is not None:
        contribution = max(-10, min(10, north_5d / 5))  # ~1 point per billion
        score += contribution

    # Margin net buy: -5 to +5
    margin_5d = indicators.get('margin_net_buy', {}).get('sum_5d')
    if margin_5d is not None:
        contribution = max(-5, min(5, margin_5d * 2))
        score += contribution

    # New high / low ratio: -10 to +10
    nh = indicators.get('new_high_low', {}).get('high')
    nl = indicators.get('new_high_low', {}).get('low')
    if nh is not None and nl is not None:
        if nh + nl > 0:
            ratio = nh / (nh + nl)  # 0 to 1
            contribution = (ratio - 0.5) * 20  # -10 to +10
            score += contribution

    # Seal rate: -5 to +5
    seal = indicators.get('seal_rate', {}).get('value')
    if seal is not None:
        if seal > 70:
            score += 5
        elif seal > 60:
            score += 2
        elif seal < 40:
            score -= 5
        elif seal < 50:
            score -= 2

    return max(0, min(100, int(score)))


# ---------------------------------------------------------------------------
# Section 4: Style Rotation
# ---------------------------------------------------------------------------

def calc_style() -> dict:
    """
    Style rotation: large vs small cap, growth vs value.
    Reuses existing market_overview tri-prism calculations.
    """
    try:
        from data_analyst.market_overview.calculator import calc_scale_rotation, calc_style_rotation, calc_anchor_5y

        scale = calc_scale_rotation()
        style = calc_style_rotation()
        anchor = calc_anchor_5y()

        result = {'available': True}

        # Scale rotation
        if scale.get('available'):
            direction = scale.get('direction', 'neutral')
            strength = scale.get('strength', 'neutral')
            result['scale'] = {
                'direction': direction,
                'strength': strength,
                'label': C.STYLE_LABELS.get(direction, direction),
                'strength_label': C.STRENGTH_LABELS.get(strength, ''),
                'signals': scale.get('signals'),
                'total': scale.get('total'),
            }
        else:
            result['scale'] = {'direction': 'unknown', 'label': '数据不足'}

        # Style rotation
        if style.get('available'):
            direction = style.get('direction', 'neutral')
            strength = style.get('strength', 'neutral')
            result['style'] = {
                'direction': direction,
                'strength': strength,
                'label': C.STYLE_LABELS.get(direction, direction),
                'strength_label': C.STRENGTH_LABELS.get(strength, ''),
                'signals': style.get('signals'),
                'total': style.get('total'),
            }
        else:
            result['style'] = {'direction': 'unknown', 'label': '数据不足'}

        # 5-year anchor
        if anchor.get('available'):
            result['anchor_5y'] = {
                'deviation_pct': anchor.get('deviation_pct'),
                'signal': anchor.get('signal'),
                'signal_text': anchor.get('signal_text'),
                'current': anchor.get('current'),
                'ma5y': anchor.get('ma5y'),
            }
        else:
            result['anchor_5y'] = {'deviation_pct': None, 'signal': 'unknown'}

        return result
    except Exception as e:
        logger.error("calc_style failed: %s", e)
        return {'available': False, 'error': str(e)}


# ---------------------------------------------------------------------------
# Section 5: Stock-Bond Dynamics
# ---------------------------------------------------------------------------

def calc_stock_bond() -> dict:
    """
    Stock-bond dynamics: stocks vs bonds relative value.
    Reuses existing market_overview calculations.
    """
    try:
        from data_analyst.market_overview.calculator import (
            calc_stock_bond_spread,
            calc_dividend_tracking,
            calc_equity_fund_rolling,
        )

        spread = calc_stock_bond_spread()
        dividend = calc_dividend_tracking()
        fund_rolling = calc_equity_fund_rolling()

        result = {'available': True}

        # Stock-bond spread
        if spread.get('available'):
            cn_spread = spread.get('spread_cn')
            if cn_spread is not None:
                if cn_spread >= 3:
                    level = 'stock_attractive'
                elif cn_spread <= 1:
                    level = 'bond_preferred'
                else:
                    level = 'neutral'
            else:
                level = 'neutral'

            result['spread'] = {
                'earnings_yield': spread.get('earnings_yield_pct'),
                'cn_bond': spread.get('cn_bond_yield'),
                'spread_cn': cn_spread,
                'signal': spread.get('signal_cn'),
                'pe': spread.get('pe'),
            }
            result['level'] = level
            result['level_label'] = C.STOCK_BOND_LABELS.get(level, level)

            # Series for sparkline
            if spread.get('series'):
                result['spread_series'] = [
                    {'date': p.get('date'), 'value': p.get('spread_cn')}
                    for p in (spread.get('series') or [])[-60:]
                    if p.get('spread_cn') is not None
                ]
            else:
                result['spread_series'] = []
        else:
            result['spread'] = {'spread_cn': None}
            result['level'] = 'neutral'
            result['level_label'] = C.STOCK_BOND_LABELS['neutral']
            result['spread_series'] = []

        # Dividend tracking
        if dividend.get('available'):
            ys = dividend.get('yield_spread', {})
            result['dividend'] = {
                'div_yield': ys.get('div_yield'),
                'spread': ys.get('spread'),
                'signal': ys.get('signal'),
            }
        else:
            result['dividend'] = {'div_yield': None}

        # Fund 3-year rolling
        if fund_rolling.get('available'):
            result['fund_rolling'] = {
                'current_pct': fund_rolling.get('current_pct'),
                'signal': fund_rolling.get('signal'),
                'signal_text': fund_rolling.get('signal_text'),
            }
        else:
            result['fund_rolling'] = {'current_pct': None}

        return result
    except Exception as e:
        logger.error("calc_stock_bond failed: %s", e)
        return {'available': False, 'error': str(e)}


# ---------------------------------------------------------------------------
# Section 6: Macro Backdrop
# ---------------------------------------------------------------------------

def calc_macro() -> dict:
    """
    Macro backdrop: tailwind or headwind for stocks?
    Reuses existing macro_pulse + adds VIX context.
    """
    try:
        from data_analyst.market_overview.calculator import calc_macro_pulse

        pulse = calc_macro_pulse()
        result = {'available': True, 'indicators': {}}

        if pulse.get('available') is False:
            return {'available': False, 'error': pulse.get('error')}

        # Copy sub-indicators
        for key in ['pmi_mfg', 'm2_yoy', 'ah_premium', 'qvix', 'north_flow']:
            if key in pulse:
                result['indicators'][key] = pulse[key]

        # Add VIX from sentiment
        try:
            fear_rows = execute_query(
                "SELECT vix, vix_level FROM trade_fear_index ORDER BY trade_date DESC LIMIT 1"
            )
            if fear_rows:
                result['indicators']['vix'] = {
                    'value': _safe_round(fear_rows[0]['vix'], 2),
                    'level': fear_rows[0].get('vix_level', ''),
                }
        except Exception:
            pass

        # Composite macro level
        score = 0
        # PMI: +1 expansion, -1 contraction
        pmi = pulse.get('pmi_mfg', {}).get('value')
        if pmi is not None:
            score += 1 if pmi >= 50 else -1

        # M2: higher is more accommodative
        m2 = pulse.get('m2_yoy', {}).get('value')
        if m2 is not None:
            score += 1 if m2 > 8 else (-1 if m2 < 7 else 0)

        # AH premium (%): too high is a headwind (A-shares expensive vs H-shares)
        # Data is in percentage format (e.g. 11.54 means A-shares are 11.54% above H-shares)
        ah = pulse.get('ah_premium', {}).get('value')
        if ah is not None:
            score += -1 if ah > 30 else (1 if ah < 15 else 0)

        if score >= 2:
            level = 'tailwind'
        elif score <= -2:
            level = 'headwind'
        else:
            level = 'neutral'

        result['level'] = level
        result['level_label'] = C.MACRO_LABELS.get(level, level)
        result['macro_score'] = score

        return result
    except Exception as e:
        logger.error("calc_macro failed: %s", e)
        return {'available': False, 'error': str(e)}


# ---------------------------------------------------------------------------
# Signal Change Log
# ---------------------------------------------------------------------------

def get_signal_log(days: int = 7) -> list:
    """
    Get recent signal change log entries from trade_dashboard_signal_log.
    Returns empty list if table doesn't exist yet.
    """
    try:
        cutoff = (date.today() - timedelta(days=days)).strftime('%Y-%m-%d')
        rows = execute_query(
            "SELECT trade_date, section, signal_from, signal_to, trigger_detail "
            "FROM trade_dashboard_signal_log "
            "WHERE trade_date >= %s ORDER BY trade_date DESC, id DESC",
            (cutoff,),
        )
        return [
            {
                'date': r['trade_date'].strftime('%Y-%m-%d') if hasattr(r['trade_date'], 'strftime') else str(r['trade_date']),
                'section': r['section'],
                'from': r['signal_from'],
                'to': r['signal_to'],
                'detail': r.get('trigger_detail', ''),
            }
            for r in rows
        ]
    except Exception:
        # Table may not exist yet
        return []


# ---------------------------------------------------------------------------
# Master function
# ---------------------------------------------------------------------------

def _get_latest_trade_date() -> str:
    """Get the latest trade date from macro_data (most recent data point)."""
    try:
        rows = execute_query(
            "SELECT MAX(date) as max_date FROM macro_data WHERE indicator='idx_csi300'"
        )
        if rows and rows[0]['max_date']:
            return rows[0]['max_date'].strftime('%Y-%m-%d')
    except Exception:
        pass
    return date.today().strftime('%Y-%m-%d')


def compute_dashboard() -> dict:
    """
    Compute the full 6-section market dashboard.
    Returns a JSON-serializable dict.
    """
    logger.info("Computing market dashboard...")
    latest_td = _get_latest_trade_date()
    today_str = date.today().strftime('%Y-%m-%d')

    # Determine freshness: data is fresh if latest trade date is today or
    # at most 1 calendar day old (e.g. weekend query on Saturday for Friday data)
    try:
        from datetime import datetime as _dt
        latest_dt = _dt.strptime(latest_td, '%Y-%m-%d').date()
        is_fresh = (date.today() - latest_dt).days <= 1
    except Exception:
        is_fresh = False

    result = {
        'updated_at': latest_td,
        'data_date': latest_td,
        'target_date': today_str,
        'is_fresh': is_fresh,
        'temperature': calc_temperature(),
        'trend': calc_trend(),
        'sentiment': calc_sentiment(),
        'style': calc_style(),
        'stock_bond': calc_stock_bond(),
        'macro': calc_macro(),
        'signal_log': get_signal_log(days=7),
    }
    logger.info("Market dashboard computed successfully")
    return result
