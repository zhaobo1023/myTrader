# -*- coding: utf-8 -*-
"""
Market overview signal calculator.
Reads from macro_data table, computes derived signals for the dashboard.
No emoji - plain text labels only.
"""
import os
import sys
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from config.db import execute_query


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_series(indicator: str, days: int = 1500) -> pd.Series:
    """Load a single indicator from macro_data as a float Series indexed by date."""
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


def _to_series_json(s: pd.Series, tail: int = 500) -> list:
    """Return last N non-null rows as list of {date, value} dicts."""
    sub = s.dropna().tail(tail)
    return [
        {'date': d.strftime('%Y-%m-%d'), 'value': round(float(v), 4)}
        for d, v in sub.items()
    ]


def _signal(value: float, thresholds: list, labels: list) -> str:
    """
    thresholds: ascending list e.g. [-10, 20]
    labels: len(thresholds)+1 labels from lowest to highest bucket
    Returns labels[i] where value < thresholds[i], else labels[-1]
    """
    for i, t in enumerate(thresholds):
        if value < t:
            return labels[i]
    return labels[-1]


# ---------------------------------------------------------------------------
# Signal calculators
# ---------------------------------------------------------------------------

def calc_anchor_5y() -> dict:
    """Compute zhongzheng quanA vs 5-year moving average signal."""
    try:
        s = _load_series('idx_all_a', days=3000)
        if len(s) < 100:
            return {'available': False}

        ma5y = s.rolling(window=1250, min_periods=250).mean()
        deviation = (s - ma5y) / ma5y * 100

        current = float(s.iloc[-1])
        current_ma = float(ma5y.iloc[-1]) if not pd.isna(ma5y.iloc[-1]) else None
        current_dev = float(deviation.iloc[-1]) if not pd.isna(deviation.iloc[-1]) else None
        last_date = s.index[-1].strftime('%Y-%m-%d')

        sig = _signal(current_dev or 0, thresholds=[-10, 20], labels=['undervalued', 'neutral', 'overvalued'])
        sig_text = {'undervalued': 'low', 'neutral': 'fair', 'overvalued': 'high'}[sig]

        combined = pd.DataFrame({'value': s, 'ma5y': ma5y, 'deviation': deviation}).dropna(subset=['value'])
        series = [
            {
                'date': d.strftime('%Y-%m-%d'),
                'value': round(float(r['value']), 2),
                'ma5y': round(float(r['ma5y']), 2) if not pd.isna(r['ma5y']) else None,
                'deviation': round(float(r['deviation']), 2) if not pd.isna(r['deviation']) else None,
            }
            for d, r in combined.tail(500).iterrows()
        ]

        return {
            'available': True,
            'last_date': last_date,
            'current': round(current, 2),
            'ma5y': round(current_ma, 2) if current_ma is not None else None,
            'deviation_pct': round(current_dev, 2) if current_dev is not None else None,
            'signal': sig,
            'signal_text': sig_text,
            'series': series,
        }
    except Exception as e:
        return {'available': False, 'error': str(e)}


def calc_stock_bond_spread() -> dict:
    """Compute PE倒数 vs bond yields (earnings yield spread)."""
    try:
        pe = _load_series('pe_csi300', days=2000).dropna()
        cn = _load_series('cn_10y_bond', days=2000).dropna()
        us = _load_series('us_10y_bond', days=2000).dropna()

        if pe.empty or cn.empty:
            return {'available': False}

        all_dates = cn.index.union(us.index).sort_values()
        pe_daily = pe.reindex(all_dates).ffill()
        ep = 100.0 / pe_daily

        spread_cn = (ep - cn).dropna()
        spread_us = (ep - us).dropna()

        def _last(s):
            return round(float(s.iloc[-1]), 3) if not s.empty else None

        cur_ep = _last(ep)
        cur_cn = _last(cn)
        cur_us = _last(us)
        cur_spread_cn = _last(spread_cn)
        cur_spread_us = _last(spread_us)
        last_date = cn.index[-1].strftime('%Y-%m-%d')

        sig_cn = _signal(cur_spread_cn or 0, [1, 3], ['expensive', 'neutral', 'attractive'])
        sig_us = _signal(cur_spread_us or 0, [0, 2], ['expensive', 'neutral', 'attractive'])
        label = {'attractive': 'attractive', 'neutral': 'neutral', 'expensive': 'expensive'}

        merged = pd.DataFrame({
            'ep': ep, 'cn': cn, 'us': us,
            'spread_cn': spread_cn, 'spread_us': spread_us,
        }).dropna(subset=['ep', 'cn'])
        series = [
            {
                'date': d.strftime('%Y-%m-%d'),
                'ep': round(float(r['ep']), 3),
                'cn_bond': round(float(r['cn']), 3) if not pd.isna(r['cn']) else None,
                'us_bond': round(float(r['us']), 3) if not pd.isna(r['us']) else None,
                'spread_cn': round(float(r['spread_cn']), 3) if not pd.isna(r['spread_cn']) else None,
                'spread_us': round(float(r['spread_us']), 3) if not pd.isna(r['spread_us']) else None,
            }
            for d, r in merged.tail(500).iterrows()
        ]

        return {
            'available': True,
            'last_date': last_date,
            'pe': round(float(pe.iloc[-1]), 2) if not pe.empty else None,
            'earnings_yield_pct': cur_ep,
            'cn_bond_yield': cur_cn,
            'us_bond_yield': cur_us,
            'spread_cn': cur_spread_cn,
            'spread_us': cur_spread_us,
            'signal_cn': sig_cn,
            'signal_us': sig_us,
            'signal_cn_text': label[sig_cn],
            'signal_us_text': label[sig_us],
            'series': series,
        }
    except Exception as e:
        return {'available': False, 'error': str(e)}


def _calc_tri_prism(key_a: str, key_b: str, name_a: str, name_b: str) -> dict:
    """
    Generic tri-prism rotation calculator using three signals:
    Bollinger Bands (252d), 5Y MA, and 40d momentum diff.
    """
    try:
        a = _load_series(key_a, days=3500)
        b = _load_series(key_b, days=3500)
        if len(a) < 300 or len(b) < 300:
            return {'available': False}

        merged = pd.DataFrame({'a': a, 'b': b}).dropna()
        ratio = merged['a'] / merged['b']

        # Signal 1: Bollinger (252d, 2std)
        roll_mean = ratio.rolling(252, min_periods=100).mean()
        roll_std = ratio.rolling(252, min_periods=100).std()
        upper = roll_mean + 2 * roll_std
        lower = roll_mean - 2 * roll_std
        boll_sig = 0
        cur_ratio = ratio.iloc[-1]
        if not pd.isna(upper.iloc[-1]) and not pd.isna(lower.iloc[-1]):
            if cur_ratio > upper.iloc[-1]:
                boll_sig = 1
            elif cur_ratio < lower.iloc[-1]:
                boll_sig = -1

        # Signal 2: 5Y MA
        ma5y = ratio.rolling(1250, min_periods=250).mean()
        ma_sig = 0
        if not pd.isna(ma5y.iloc[-1]):
            ma_sig = 1 if cur_ratio > ma5y.iloc[-1] else -1

        # Signal 3: 40d momentum diff
        ret_diff = merged['a'].pct_change(40) - merged['b'].pct_change(40)
        diff_ma = ret_diff.rolling(252, min_periods=100).mean()
        mom_sig = 0
        if not pd.isna(ret_diff.iloc[-1]) and not pd.isna(diff_ma.iloc[-1]):
            mom_sig = 1 if ret_diff.iloc[-1] > diff_ma.iloc[-1] else -1

        total = boll_sig + ma_sig + mom_sig
        if total >= 2:
            direction, strength = name_a, 'confirmed'
        elif total <= -2:
            direction, strength = name_b, 'confirmed'
        elif total == 1:
            direction, strength = name_a, 'weak'
        elif total == -1:
            direction, strength = name_b, 'weak'
        else:
            direction, strength = 'neutral', 'neutral'

        series_df = pd.DataFrame({
            'ratio': ratio, 'upper': upper, 'lower': lower, 'ma5y': ma5y,
        }).dropna(subset=['ratio'])
        series = [
            {
                'date': d.strftime('%Y-%m-%d'),
                'ratio': round(float(r['ratio']), 4),
                'upper': round(float(r['upper']), 4) if not pd.isna(r['upper']) else None,
                'lower': round(float(r['lower']), 4) if not pd.isna(r['lower']) else None,
                'ma5y': round(float(r['ma5y']), 4) if not pd.isna(r['ma5y']) else None,
            }
            for d, r in series_df.tail(500).iterrows()
        ]

        return {
            'available': True,
            'last_date': merged.index[-1].strftime('%Y-%m-%d'),
            'signals': {'boll': boll_sig, 'ma5y': ma_sig, 'momentum40d': mom_sig},
            'total': total,
            'direction': direction,
            'strength': strength,
            'name_a': name_a,
            'name_b': name_b,
            'series': series,
        }
    except Exception as e:
        return {'available': False, 'error': str(e)}


def calc_scale_rotation() -> dict:
    """Large cap vs small cap rotation signal."""
    return _calc_tri_prism('idx_csi300', 'idx_csi1000', 'large_cap', 'small_cap')


def calc_style_rotation() -> dict:
    """Growth vs value rotation signal."""
    return _calc_tri_prism('idx_growth300', 'idx_value300', 'growth', 'value')


def calc_dividend_tracking() -> dict:
    """Track dividend yield spread and relative returns for dividend indices."""
    try:
        dy = _load_series('div_yield_csi300', days=2000).dropna()
        cn = _load_series('cn_10y_bond', days=2000).dropna()
        div_idx = _load_series('idx_dividend', days=400)
        all_a_idx = _load_series('idx_all_a', days=400)
        hk_div = _load_series('idx_hk_dividend', days=400)

        result = {'available': True}

        # a) Yield spread
        if not dy.empty and not cn.empty:
            all_dates = cn.index.sort_values()
            dy_daily = dy.reindex(all_dates).ffill()
            spread = (dy_daily - cn).dropna()
            cur_spread = round(float(spread.iloc[-1]), 3) if not spread.empty else None
            sig = _signal(cur_spread or 0, [1, 3], ['normal', 'attractive', 'very_attractive'])
            label = {'normal': 'normal', 'attractive': 'attractive', 'very_attractive': 'very_attractive'}
            dy_series = pd.DataFrame({'dy': dy_daily, 'cn': cn, 'spread': spread}).dropna(subset=['dy'])
            result['yield_spread'] = {
                'div_yield': round(float(dy.iloc[-1]), 3),
                'cn_bond': round(float(cn.iloc[-1]), 3),
                'spread': cur_spread,
                'signal': sig,
                'signal_text': label[sig],
                'series': [
                    {
                        'date': d.strftime('%Y-%m-%d'),
                        'div_yield': round(float(r['dy']), 3),
                        'cn_bond': round(float(r['cn']), 3) if not pd.isna(r['cn']) else None,
                        'spread': round(float(r['spread']), 3) if not pd.isna(r['spread']) else None,
                    }
                    for d, r in dy_series.tail(300).iterrows()
                ],
            }
        else:
            result['yield_spread'] = {'available': False}

        # b) Dividend vs full-A 40d relative return
        if not div_idx.empty and not all_a_idx.empty:
            m = pd.DataFrame({'div': div_idx, 'all': all_a_idx}).dropna()
            diff = (m['div'].pct_change(40) - m['all'].pct_change(40)) * 100
            diff = diff.dropna()
            cur_diff = round(float(diff.iloc[-1]), 2) if not diff.empty else None
            sig2 = _signal(cur_diff or 0, [-5, 8], ['buy_opportunity', 'neutral', 'overextended'])
            label2 = {'buy_opportunity': 'buy_opportunity', 'neutral': 'neutral', 'overextended': 'overextended'}
            result['rel_return_40d'] = {
                'value': cur_diff,
                'signal': sig2,
                'signal_text': label2[sig2],
                'series': _to_series_json(diff, tail=300),
            }
        else:
            result['rel_return_40d'] = {'available': False}

        # c) Dividend A vs HK 40d
        if not div_idx.empty and not hk_div.empty:
            m2 = pd.DataFrame({'a': div_idx, 'hk': hk_div}).dropna()
            diff2 = (m2['a'].pct_change(40) - m2['hk'].pct_change(40)) * 100
            diff2 = diff2.dropna()
            cur_diff2 = round(float(diff2.iloc[-1]), 2) if not diff2.empty else None
            sig3 = _signal(cur_diff2 or 0, [-5, 5], ['hk_preferred', 'neutral', 'a_preferred'])
            label3 = {'hk_preferred': 'hk_preferred', 'neutral': 'neutral', 'a_preferred': 'a_preferred'}
            result['ah_rel_return_40d'] = {
                'value': cur_diff2,
                'signal': sig3,
                'signal_text': label3[sig3],
                'series': _to_series_json(diff2, tail=300),
            }
        else:
            result['ah_rel_return_40d'] = {'available': False}

        return result
    except Exception as e:
        return {'available': False, 'error': str(e)}


def calc_equity_fund_rolling() -> dict:
    """3-year rolling annualized return of equity fund index."""
    try:
        s = _load_series('idx_equity_fund', days=3500)
        if len(s) < 756:
            return {'available': False}

        roll3y = s.pct_change(756) * 100
        ann = ((1 + roll3y / 100) ** (1.0 / 3) - 1) * 100
        cur = round(float(ann.iloc[-1]), 2) if not pd.isna(ann.iloc[-1]) else None
        last_date = s.index[-1].strftime('%Y-%m-%d')
        sig = _signal(cur or 0, [-10, 30], ['bottom', 'normal', 'bubble'])
        label = {'bottom': 'bottom', 'normal': 'normal', 'bubble': 'bubble'}

        return {
            'available': True,
            'last_date': last_date,
            'current_pct': cur,
            'signal': sig,
            'signal_text': label[sig],
            'series': _to_series_json(ann.dropna(), tail=500),
        }
    except Exception as e:
        return {'available': False, 'error': str(e)}


def calc_macro_pulse() -> dict:
    """Snapshot of key macro indicators: qvix, northbound flow, M2, PMI, AH premium."""
    try:
        def _latest(ind, days=45):
            s = _load_series(ind, days=days)
            return round(float(s.iloc[-1]), 3) if not s.empty else None

        qvix = _latest('qvix')
        m2 = _latest('m2_yoy')
        pmi = _latest('pmi_mfg')
        ah = _latest('ah_premium', days=10)

        north_rows = execute_query(
            "SELECT date, value FROM macro_data WHERE indicator='north_flow' AND value IS NOT NULL ORDER BY date DESC LIMIT 5"
        )
        north_today = float(north_rows[0]['value']) if north_rows and north_rows[0]['value'] is not None else None
        north_5d = sum(float(r['value']) for r in north_rows if r['value'] is not None) if north_rows else None

        qvix_sig = _signal(qvix or 20, [15, 25, 35], ['complacent', 'normal', 'fearful', 'panic'])
        qvix_labels = {
            'complacent': 'complacent', 'normal': 'normal',
            'fearful': 'fearful', 'panic': 'panic',
        }

        return {
            'qvix': {'value': qvix, 'signal': qvix_sig, 'signal_text': qvix_labels[qvix_sig]},
            'north_flow': {
                'today': north_today,
                'sum_5d': round(north_5d, 2) if north_5d is not None else None,
                'signal': 'inflow' if (north_5d or 0) > 0 else 'outflow',
            },
            'm2_yoy': {'value': m2},
            'pmi_mfg': {
                'value': pmi,
                'signal': 'unknown' if pmi is None else ('expansion' if pmi >= 50 else 'contraction'),
                'signal_text': 'unknown' if pmi is None else ('expansion' if pmi >= 50 else 'contraction'),
            },
            'ah_premium': {
                'value': ah,
                'signal': 'unknown' if ah is None else _signal(ah, [15, 30], ['low', 'moderate', 'high']),
                'signal_text': 'unknown' if ah is None else ('low' if ah < 15 else ('moderate' if ah < 30 else 'high')),
            },
        }
    except Exception as e:
        return {'available': False, 'error': str(e)}


def calc_market_turnover() -> dict:
    """Average market turnover rate from trade_stock_daily."""
    try:
        rows = execute_query("""
            SELECT trade_date, AVG(turnover_rate) AS avg_tr
            FROM trade_stock_daily
            WHERE trade_date >= DATE_SUB(CURDATE(), INTERVAL 400 DAY)
              AND turnover_rate > 0
            GROUP BY trade_date
            ORDER BY trade_date
        """)
        if not rows:
            return {'available': False}

        s = pd.Series({r['trade_date']: float(r['avg_tr']) for r in rows})
        s.index = pd.to_datetime(s.index)
        s = s.sort_index().dropna()
        if s.empty:
            return {'available': False}

        cur = round(float(s.iloc[-1]), 3)
        window = s.tail(252)
        pct_rank = round(float((window < cur).mean() * 100), 1) if len(window) > 10 else None
        sig = _signal(cur, [0.8, 3.0], ['low', 'normal', 'high'])
        label = {'low': 'low', 'normal': 'normal', 'high': 'high'}

        return {
            'available': True,
            'last_date': s.index[-1].strftime('%Y-%m-%d'),
            'value': cur,
            'pct_rank': pct_rank,
            'signal': sig,
            'signal_text': label[sig],
            'series': _to_series_json(s, tail=252),
        }
    except Exception as e:
        return {'available': False, 'error': str(e)}


# ---------------------------------------------------------------------------
# Master function
# ---------------------------------------------------------------------------

def compute_all() -> dict:
    """Compute all 8 market overview signal groups."""
    return {
        'updated_at': date.today().strftime('%Y-%m-%d'),
        'anchor_5y': calc_anchor_5y(),
        'stock_bond_spread': calc_stock_bond_spread(),
        'scale_rotation': calc_scale_rotation(),
        'style_rotation': calc_style_rotation(),
        'dividend': calc_dividend_tracking(),
        'equity_fund_rolling': calc_equity_fund_rolling(),
        'macro_pulse': calc_macro_pulse(),
        'market_turnover': calc_market_turnover(),
    }
