"""
Fear & Greed Index Service (v2)

Multi-dimensional composite index inspired by CNN Fear & Greed,
adapted for A-share + global macro context.

7 dimensions, each scored 0-100 (0=extreme fear, 100=extreme greed):
  1. Volatility     -- QVIX / VIX level
  2. Market Momentum -- CSI300 vs 60-day MA
  3. Breadth        -- advance/decline ratio
  4. Price Strength  -- limit-up vs limit-down
  5. Safe Haven     -- US 10Y yield change (rising = fear)
  6. Capital Flow   -- North-bound net flow
  7. Valuation      -- CSI300 PE percentile (5-year)

Final score = weighted average of available dimensions.
Data sourced from macro_data table (no yfinance dependency at runtime).
"""

import logging
from typing import Optional
from datetime import datetime, date, timedelta

from data_analyst.sentiment.config import VIX_THRESHOLDS, US10Y_THRESHOLDS, DATA_SOURCE_CONFIG
from data_analyst.sentiment.schemas import FearIndexResult

logger = logging.getLogger(__name__)


def _query_macro(indicator: str, days: int = 30) -> list:
    """Query recent values from macro_data, newest first."""
    from config.db import execute_query
    cutoff = (date.today() - timedelta(days=days + 5)).strftime('%Y-%m-%d')
    rows = list(execute_query(
        "SELECT date, value FROM macro_data WHERE indicator = %s AND date >= %s ORDER BY date DESC",
        (indicator, cutoff),
    ))
    return [(r['date'], float(r['value'])) for r in rows if r['value'] is not None]


def _latest(indicator: str) -> Optional[float]:
    pts = _query_macro(indicator, days=5)
    return pts[0][1] if pts else None


def _ma(indicator: str, window: int) -> Optional[float]:
    pts = _query_macro(indicator, days=window + 10)
    vals = [v for _, v in pts[:window]]
    return sum(vals) / len(vals) if len(vals) >= window * 0.8 else None


# ---------------------------------------------------------------------------
# Dimension scorers (each returns 0-100 or None if data missing)
# ---------------------------------------------------------------------------

def _score_volatility() -> tuple:
    """QVIX-based volatility dimension. Low vol = greed, high vol = fear."""
    qvix = _latest('qvix')
    vix = _latest('vix')
    val = qvix or vix
    if val is None:
        return None, {'qvix': qvix, 'vix': vix}
    # QVIX/VIX typical range: 10-50
    if val < 13:
        score = 90  # extreme greed (complacency)
    elif val < 17:
        score = 70
    elif val < 22:
        score = 50
    elif val < 30:
        score = 25
    else:
        score = 5   # extreme fear
    return score, {'qvix': qvix, 'vix': vix, 'used': val}


def _score_momentum() -> tuple:
    """CSI300 price vs 60-day MA. Above MA = greed, below = fear."""
    price = _latest('idx_csi300')
    ma60 = _ma('idx_csi300', 60)
    if price is None or ma60 is None or ma60 == 0:
        return None, {'price': price, 'ma60': ma60}
    pct = (price - ma60) / ma60 * 100  # deviation %
    # Map: -10% -> 0, 0% -> 50, +10% -> 100
    score = max(0, min(100, 50 + pct * 5))
    return int(score), {'price': round(price, 2), 'ma60': round(ma60, 2), 'deviation_pct': round(pct, 2)}


def _score_breadth() -> tuple:
    """Advance/decline ratio. More advancers = greed."""
    adv = _latest('advance_count')
    dec = _latest('decline_count')
    if adv is None or dec is None:
        return None, {'advance': adv, 'decline': dec}
    total = adv + dec
    if total == 0:
        return 50, {'advance': adv, 'decline': dec}
    ratio = adv / total
    # Map: 0.3 -> 10, 0.5 -> 50, 0.7 -> 90
    score = max(0, min(100, (ratio - 0.3) / 0.4 * 100))
    return int(score), {'advance': int(adv), 'decline': int(dec), 'ratio': round(ratio, 3)}


def _score_price_strength() -> tuple:
    """Limit-up vs limit-down count. More limit-ups = greed."""
    up = _latest('limit_up_count')
    down = _latest('limit_down_count')
    if up is None or down is None:
        return None, {'limit_up': up, 'limit_down': down}
    total = up + down
    if total == 0:
        return 50, {'limit_up': int(up), 'limit_down': int(down)}
    ratio = up / total
    score = max(0, min(100, ratio * 100))
    return int(score), {'limit_up': int(up), 'limit_down': int(down), 'ratio': round(ratio, 3)}


def _score_safe_haven() -> tuple:
    """US 10Y yield: rising yield = fear (money leaving risk assets)."""
    pts = _query_macro('us_10y_bond', days=10)
    if len(pts) < 2:
        return None, {}
    current = pts[0][1]
    prev_5d = pts[min(4, len(pts) - 1)][1]
    change = current - prev_5d  # in percentage points
    # Rising rates (+0.2) = fear, falling (-0.2) = greed
    # Map: -0.3 -> 90, 0 -> 50, +0.3 -> 10
    score = max(0, min(100, 50 - change * 130))
    return int(score), {'current': current, 'change_5d': round(change, 3)}


def _score_capital_flow() -> tuple:
    """North-bound capital flow. Net inflow = greed, outflow = fear."""
    pts = _query_macro('north_flow', days=10)
    if not pts:
        return None, {}
    # Sum last 5 days
    vals = [v for _, v in pts[:5]]
    flow_5d = sum(vals)
    # Typical range: -200 ~ +200 (亿)
    score = max(0, min(100, 50 + flow_5d / 4))
    return int(score), {'flow_5d': round(flow_5d, 2), 'days': len(vals)}


def _score_valuation() -> tuple:
    """CSI300 PE percentile in recent history. High PE = greed, low = fear."""
    pts = _query_macro('pe_csi300', days=365 * 3)
    if len(pts) < 20:
        return None, {}
    current = pts[0][1]
    all_vals = sorted([v for _, v in pts])
    # Percentile rank
    rank = sum(1 for v in all_vals if v <= current) / len(all_vals) * 100
    return int(rank), {'pe': current, 'percentile': round(rank, 1), 'sample_size': len(all_vals)}


# ---------------------------------------------------------------------------
# Composite index
# ---------------------------------------------------------------------------

DIMENSIONS = [
    ('volatility',      '波动率',     _score_volatility,      0.20),
    ('momentum',        '市场动量',   _score_momentum,        0.15),
    ('breadth',         '涨跌广度',   _score_breadth,         0.15),
    ('price_strength',  '涨跌停强度', _score_price_strength,  0.10),
    ('safe_haven',      '避险需求',   _score_safe_haven,      0.15),
    ('capital_flow',    '资金流向',   _score_capital_flow,    0.15),
    ('valuation',       '估值水位',   _score_valuation,       0.10),
]


class FearIndexService:
    """Multi-dimensional Fear & Greed Index (v2)"""

    def __init__(self):
        self.config = DATA_SOURCE_CONFIG['yfinance']

    def get_fear_index(self) -> FearIndexResult:
        """Calculate composite fear & greed index from macro_data."""
        logger.info("Calculating multi-dimensional fear & greed index...")

        dimensions = []
        weighted_sum = 0.0
        weight_sum = 0.0

        for key, label, scorer, weight in DIMENSIONS:
            try:
                score, detail = scorer()
            except Exception as e:
                logger.warning("Dimension %s failed: %s", key, e)
                score, detail = None, {'error': str(e)}

            dimensions.append({
                'key': key,
                'label': label,
                'score': score,
                'weight': weight,
                'detail': detail,
            })

            if score is not None:
                weighted_sum += score * weight
                weight_sum += weight

        # Composite score (re-normalize weights for available dimensions)
        composite = int(weighted_sum / weight_sum) if weight_sum > 0 else 50

        # Determine regime
        if composite <= 20:
            regime = 'extreme_fear'
        elif composite <= 40:
            regime = 'fear'
        elif composite <= 60:
            regime = 'neutral'
        elif composite <= 80:
            regime = 'greed'
        else:
            regime = 'extreme_greed'

        regime_labels = {
            'extreme_fear': '极度恐慌',
            'fear': '恐慌',
            'neutral': '中性',
            'greed': '贪婪',
            'extreme_greed': '极度贪婪',
        }

        # Extract individual values for backward compatibility
        vix = _latest('vix')
        qvix = _latest('qvix')
        us10y = _latest('us_10y_bond')

        vix_val = vix or qvix
        vix_level = '数据缺失'
        if vix_val is not None:
            if vix_val < 15:
                vix_level = '极度平静(警惕自满)'
            elif vix_val < 20:
                vix_level = '正常'
            elif vix_val < 25:
                vix_level = '焦虑'
            elif vix_val < 35:
                vix_level = '恐慌'
            else:
                vix_level = '极度恐慌'

        us10y_strategy = '数据缺失'
        if us10y is not None:
            if us10y > 4.8:
                us10y_strategy = '利率偏高，看好价值股和防御板块'
            elif us10y > 4.5:
                us10y_strategy = '利率处于中性偏高，关注方向选择'
            elif us10y > 4.0:
                us10y_strategy = '利率中性，成长与价值均衡配置'
            elif us10y > 3.5:
                us10y_strategy = '利率偏低，资金偏好成长股'
            else:
                us10y_strategy = '宽松预期，资金回流成长股'

        result = FearIndexResult(
            vix=vix,
            ovx=_latest('ovx'),
            gvz=_latest('gvz'),
            us10y=us10y,
            fear_greed_score=composite,
            market_regime=regime,
            vix_level=vix_level,
            us10y_strategy=us10y_strategy,
            risk_alert=None,
            timestamp=datetime.now(),
        )

        logger.info("Fear & Greed index: %d (%s), %d/%d dimensions available",
                     composite, regime_labels.get(regime, regime),
                     sum(1 for d in dimensions if d['score'] is not None), len(dimensions))

        # Attach dimensions detail to result for API exposure
        result._dimensions = dimensions  # type: ignore
        result._regime_label = regime_labels.get(regime, regime)  # type: ignore

        return result
