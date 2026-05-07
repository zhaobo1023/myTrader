# Tech Scan v2.0 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade single stock technical analysis report from v1.0 (raw indicator display) to v2.0 (scored, interpreted, actionable report with KDJ/BOLL/divergence).

**Architecture:** Add KDJ, BOLL, MACD divergence to existing `IndicatorCalculator`/`SignalDetector`. Build a new `ReportEngine` class that computes composite score, generates text interpretations, and produces structured HTML report sections. Rewrite `single_scanner.py` HTML output to use the new engine.

**Tech Stack:** Python 3.10+, pandas, numpy, matplotlib (no new dependencies)

---

## Existing Code Context

**Key files to modify:**
- `strategist/tech_scan/indicator_calculator.py` - Add KDJ, BOLL calculations
- `strategist/tech_scan/signal_detector.py` - Add MACD divergence detection, danger/opportunity signals
- `strategist/tech_scan/single_scanner.py` - Rewrite HTML report with v2.0 sections
- `strategist/tech_scan/chart_generator.py` - Add BOLL bands to chart

**Reusable existing code:**
- `data_analyst/indicators/technical.py:109-147` - KDJ calculation (TA-Lib + pandas fallback)
- `data_analyst/indicators/technical.py:149-178` - BOLL calculation (TA-Lib + pandas fallback)
- `strategist/tech_scan/data_fetcher.py` - DB already has `turnover_rate` column from `trade_stock_daily`

**DB columns available:** `open, high, low, close, volume, amount, turnover_rate`

---

### Task 1: Add KDJ and BOLL to IndicatorCalculator

**Files:**
- Modify: `strategist/tech_scan/indicator_calculator.py`

**Step 1: Add KDJ calculation method**

Add `_calc_kdj(self, df)` to `IndicatorCalculator._calc_indicators_for_stock()`. Reuse the pandas formula from `data_analyst/indicators/technical.py` (avoid TA-Lib dependency since tech_scan is self-contained):

```python
# KDJ (9,3,3) - pandas implementation matching EastMoney convention
low_n = df['low'].rolling(9, min_periods=9).min()
high_n = df['high'].rolling(9, min_periods=9).max()
rsv = (df['close'] - low_n) / (high_n - low_n) * 100
df['kdj_k'] = rsv.ewm(com=2, adjust=False).mean()  # alpha=1/3
df['kdj_d'] = df['kdj_k'].ewm(com=2, adjust=False).mean()  # alpha=1/3
df['kdj_j'] = 3 * df['kdj_k'] - 2 * df['kdj_d']
df['prev_kdj_k'] = df['kdj_k'].shift(1)
df['prev_kdj_d'] = df['kdj_d'].shift(1)
```

**Step 2: Add BOLL calculation method**

Add to `_calc_indicators_for_stock()`:

```python
# BOLL (20, 2)
boll_mid = df['close'].rolling(20, min_periods=20).mean()
boll_std = df['close'].rolling(20, min_periods=20).std()
df['boll_upper'] = boll_mid + 2 * boll_std
df['boll_lower'] = boll_mid - 2 * boll_std
df['boll_middle'] = boll_mid
df['boll_pctb'] = (df['close'] - df['boll_lower']) / (df['boll_upper'] - df['boll_lower'])
df['boll_bandwidth'] = (df['boll_upper'] - df['boll_lower']) / df['boll_middle']
```

**Step 3: Add prev_macd_hist for divergence detection**

```python
df['prev_macd_hist'] = df['macd_hist'].shift(1)
```

**Step 4: Smoke test**

Run: `DB_ENV=online python -c "
from strategist.tech_scan.data_fetcher import DataFetcher
from strategist.tech_scan.indicator_calculator import IndicatorCalculator
f = DataFetcher(env='online')
df = f.fetch_daily_data(['688386.SH'], lookback_days=300)
c = IndicatorCalculator()
df = c.calculate_all(df)
latest = df.iloc[-1]
print('KDJ:', latest.get('kdj_k'), latest.get('kdj_d'), latest.get('kdj_j'))
print('BOLL:', latest.get('boll_upper'), latest.get('boll_middle'), latest.get('boll_lower'))
print('pctB:', latest.get('boll_pctb'))
"`
Expected: Numeric values for all KDJ/BOLL columns, no errors.

**Step 5: Commit**

```bash
git add strategist/tech_scan/indicator_calculator.py
git commit -m "feat(tech-scan): add KDJ and BOLL indicators to calculator"
```

---

### Task 2: MACD Divergence Detection

**Files:**
- Modify: `strategist/tech_scan/signal_detector.py`

**Step 1: Add `detect_macd_divergence()` method to SignalDetector**

This method takes the full DataFrame (not just latest row) and looks at recent history:

```python
def detect_macd_divergence(self, df: pd.DataFrame, window: int = 60) -> dict:
    """
    Detect MACD divergence (simplified Chan theory).

    Top divergence: price makes new high but MACD histogram area shrinks.
    Bottom divergence: price makes new low but MACD histogram area shrinks.

    Args:
        df: Single-stock DataFrame with macd_hist and close columns
        window: Lookback window for analysis

    Returns:
        {'type': '顶背驰'|'底背驰'|'无背驰', 'confidence': '高'|'中'|'低', 'description': str}
    """
    if len(df) < 20:
        return {'type': '无背驰', 'confidence': '低', 'description': '数据不足，无法判断'}

    recent = df.tail(window).copy()
    histograms = recent['macd_hist'].values
    prices = recent['close'].values

    # Split histogram into segments by zero crossing
    segments = []
    current_sign = None
    current_values = []
    current_indices = []

    for i, h in enumerate(histograms):
        sign = 'positive' if h >= 0 else 'negative'
        if current_sign is None:
            current_sign = sign
            current_values = [h]
            current_indices = [i]
        elif sign == current_sign:
            current_values.append(h)
            current_indices.append(i)
        else:
            segments.append({
                'type': current_sign,
                'histograms': current_values,
                'indices': current_indices,
                'start': current_indices[0],
                'end': current_indices[-1]
            })
            current_sign = sign
            current_values = [h]
            current_indices = [i]

    if current_values:
        segments.append({
            'type': current_sign,
            'histograms': current_values,
            'indices': current_indices,
            'start': current_indices[0],
            'end': current_indices[-1]
        })

    if len(segments) < 2:
        return {'type': '无背驰', 'confidence': '低', 'description': '波段不足，无法判断'}

    last_seg = segments[-1]
    prev_seg = segments[-2]

    last_area = sum(abs(h) for h in last_seg['histograms'])
    prev_area = sum(abs(h) for h in prev_seg['histograms'])

    if prev_area == 0:
        return {'type': '无背驰', 'confidence': '低', 'description': '前一波段面积为零'}

    # Top divergence
    if last_seg['type'] == 'positive':
        last_price_high = max(prices[i] for i in last_seg['indices'])
        prev_price_high = max(prices[i] for i in prev_seg['indices'])
        if last_price_high > prev_price_high and last_area < prev_area * 0.8:
            confidence = '高' if last_area < prev_area * 0.6 else '中'
            return {
                'type': '顶背驰', 'confidence': confidence,
                'description': (f"价格创新高（{last_price_high:.2f} > {prev_price_high:.2f}），"
                    f"但MACD柱面积收缩（{last_area:.1f} < {prev_area:.1f}），"
                    f"上涨动能衰减，警惕回调风险")
            }

    # Bottom divergence
    if last_seg['type'] == 'negative':
        last_price_low = min(prices[i] for i in last_seg['indices'])
        prev_price_low = min(prices[i] for i in prev_seg['indices'])
        if last_price_low < prev_price_low and last_area < prev_area * 0.8:
            confidence = '高' if last_area < prev_area * 0.6 else '中'
            return {
                'type': '底背驰', 'confidence': confidence,
                'description': (f"价格创新低（{last_price_low:.2f} < {prev_price_low:.2f}），"
                    f"但MACD柱面积收缩（{last_area:.1f} < {prev_area:.1f}），"
                    f"下跌动能衰减，可能存在反弹机会")
            }

    return {'type': '无背驰', 'confidence': '低', 'description': '当前无明显MACD背驰信号'}
```

**Step 2: Add KDJ signal detection method**

```python
def detect_kdj_signals(self, latest: pd.Series) -> list:
    """Detect KDJ crossover and overbought/oversold signals."""
    signals = []
    k = latest.get('kdj_k')
    d = latest.get('kdj_d')
    j = latest.get('kdj_j')
    prev_k = latest.get('prev_kdj_k')
    prev_d = latest.get('prev_kdj_d')

    if any(v is None or pd.isna(v) for v in [k, d, j, prev_k, prev_d]):
        return signals

    # Golden cross / Death cross
    if k > d and prev_k <= prev_d:
        signals.append(Signal(
            name='KDJ金叉', level=SignalLevel.GREEN, severity=SignalSeverity.WARNING,
            description=f'K({k:.1f})上穿D({d:.1f})，短期买入信号'
        ))
    elif k < d and prev_k >= prev_d:
        signals.append(Signal(
            name='KDJ死叉', level=SignalLevel.RED, severity=SignalSeverity.WARNING,
            description=f'K({k:.1f})下穿D({d:.1f})，短期卖出信号'
        ))

    # Overbought / Oversold
    if j > 90:
        signals.append(Signal(
            name='KDJ超买', level=SignalLevel.YELLOW, severity=SignalSeverity.WARNING,
            description=f'J值={j:.1f}超过90，严重超买，注意回调'
        ))
    elif j > 80:
        signals.append(Signal(
            name='KDJ偏买', level=SignalLevel.YELLOW, severity=SignalSeverity.WARNING,
            description=f'J值={j:.1f}进入超买区间'
        ))
    elif j < 10:
        signals.append(Signal(
            name='KDJ超卖', level=SignalLevel.YELLOW, severity=SignalSeverity.WARNING,
            description=f'J值={j:.1f}低于10，严重超卖，关注反弹'
        ))
    elif j < 20:
        signals.append(Signal(
            name='KDJ偏卖', level=SignalLevel.INFO, severity=SignalSeverity.WARNING,
            description=f'J值={j:.1f}进入超卖区间'
        ))

    # Bottom stagnation
    if j < 20 and k < 20 and d < 20:
        signals.append(Signal(
            name='KDJ底部钝化', level=SignalLevel.GREEN, severity=SignalSeverity.WARNING,
            description='KDJ三线均在20以下，底部信号增强'
        ))

    return signals
```

**Step 3: Commit**

```bash
git add strategist/tech_scan/signal_detector.py
git commit -m "feat(tech-scan): add MACD divergence and KDJ signal detection"
```

---

### Task 3: Build ReportEngine (Scoring + Interpretation)

**Files:**
- Create: `strategist/tech_scan/report_engine.py`

This is the core new module. It takes computed indicator data and produces:
1. Composite score (0-10)
2. Text interpretation for each indicator
3. MA pattern classification
4. Volume-price quadrant analysis
5. Danger/opportunity signal list
6. Key support/resistance levels

**Step 1: Create report_engine.py with scoring system**

```python
# strategist/tech_scan/report_engine.py
"""Report engine for tech scan v2.0 - scoring, interpretation, and structured analysis."""
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict

from strategist.tech_scan.signal_detector import SignalDetector, SignalLevel


@dataclass
class ScoreResult:
    score: float           # 0-10
    trend_label: str       # e.g. "偏多"
    action_advice: str     # e.g. "持有为主，轻仓参与"


@dataclass
class MAPattern:
    name: str              # e.g. "强势空头排列"
    color: str             # "green"/"orange"/"red"/"gray"
    description: str       # text interpretation


@dataclass
class VolumePriceQuadrant:
    label: str             # e.g. "缩量下跌"
    color: str
    description: str


@dataclass
class KeyLevel:
    price: float
    source: str            # e.g. "MA20", "20日高点"
    level_type: str        # "support" or "resistance"
    strength: str          # "强"/"中"/"弱"


@dataclass
class AlertSignal:
    category: str          # "danger" or "opportunity"
    level: str             # "critical"/"high"/"medium" for danger
    name: str
    description: str


class ReportEngine:
    """Produces scored, interpreted analysis from raw indicator data."""

    def __init__(self):
        self.detector = SignalDetector()

    # --- Section 1: Scoring ---
    def calc_score(self, latest: pd.Series) -> ScoreResult:
        """Calculate composite trend score 0-10."""
        score = 0.0
        close = latest['close']

        # MA system (max 3)
        for w, pts in [(5, 0.5), (20, 1.0), (60, 1.0), (250, 0.5)]:
            ma = latest.get(f'ma{w}')
            if ma is not None and not np.isnan(ma):
                if close > ma:
                    score += pts

        # MA bullish alignment bonus
        ma5, ma20, ma60 = latest.get('ma5'), latest.get('ma20'), latest.get('ma60')
        if all(v is not None and not np.isnan(v) for v in [ma5, ma20, ma60]):
            if ma5 > ma20 > ma60:
                score += 0.5
            if ma5 < ma20:
                score -= 0.5

        # MACD (max 2)
        dif = latest.get('macd_dif', 0)
        dea = latest.get('macd_dea', 0)
        hist = latest.get('macd_hist', 0)
        prev_hist = latest.get('prev_macd_hist', 0)
        if dif > dea:
            score += 1.0
        if hist > 0:
            score += 0.5
        if hist > prev_hist:
            score += 0.5

        # KDJ (max 2)
        k = latest.get('kdj_k')
        d = latest.get('kdj_d')
        j = latest.get('kdj_j')
        if all(v is not None and not np.isnan(v) for v in [k, d, j]):
            if k > 50: score += 0.5
            if k > d: score += 0.5
            if j > 50: score += 0.5
            if j < 80: score += 0.5

        # RSI (max 1)
        rsi = latest.get('rsi')
        if rsi is not None and not np.isnan(rsi):
            if 40 < rsi < 70: score += 1.0
            elif 30 < rsi <= 40: score += 0.5

        # Volume-price (max 2)
        vr = latest.get('volume_ratio')
        pct = latest.get('pct_change', 0)
        if vr is not None and not np.isnan(vr):
            if vr > 1.2 and pct > 0: score += 1.0
            elif vr < 0.8 and pct < 0: score += 1.0
            elif vr > 1.5 and pct < 0: score -= 1.0

        score = max(0, min(10, round(score, 1)))

        # Map to label
        if score >= 8.0: label, advice = '强势多头', '积极持有，可适当加仓'
        elif score >= 6.0: label, advice = '偏多', '持有为主，轻仓参与'
        elif score >= 4.0: label, advice = '中性震荡', '观望为主，等待方向明确'
        elif score >= 2.0: label, advice = '偏空', '减仓或空仓，警惕破位'
        else: label, advice = '强势空头', '空仓，严控风险'

        return ScoreResult(score=score, trend_label=label, action_advice=advice)

    # --- Section 2: MA Pattern ---
    def classify_ma_pattern(self, latest: pd.Series) -> MAPattern:
        close = latest['close']
        ma5 = latest.get('ma5')
        ma20 = latest.get('ma20')
        ma60 = latest.get('ma60')

        if any(v is None or np.isnan(v) for v in [ma5, ma20, ma60]):
            return MAPattern('数据不足', 'gray', '均线数据不足，无法判断')

        if ma5 > ma20 > ma60:
            if close > ma5:
                return MAPattern('强势多头排列', 'green', '短中长均线多头排列，价格站上所有均线')
            else:
                return MAPattern('多头排列（回踩）', 'orange', '均线多头排列，价格短期回踩MA5')

        if ma5 < ma20 < ma60:
            if close < ma5:
                return MAPattern('强势空头排列', 'red', '短中长均线空头排列，价格跌破所有均线')
            else:
                return MAPattern('空头排列（反弹）', 'orange', '均线空头排列，价格短期反弹至MA5附近')

        if abs(ma5 - ma20) / ma20 < 0.02:
            return MAPattern('均线收口', 'yellow', 'MA5与MA20差距收窄，可能即将变盘')

        return MAPattern('均线粘合', 'gray', '均线交织，方向不明，建议观望')

    # --- Section 5: Volume-Price Quadrant ---
    def analyze_volume_price(self, latest: pd.Series) -> VolumePriceQuadrant:
        close = latest['close']
        prev_close = latest.get('prev_close', close)
        volume = latest.get('volume', 0)
        vol_ma5 = latest.get('vol_ma5', 1)

        price_up = close > prev_close
        vol_expand = volume > vol_ma5 * 1.2 if vol_ma5 > 0 else False

        if price_up and vol_expand:
            return VolumePriceQuadrant('放量上涨', 'green', '价涨量增，多头主动进攻，信号强烈')
        elif price_up and not vol_expand:
            return VolumePriceQuadrant('缩量上涨', 'yellow', '价涨量缩，上涨缺乏量能支撑，持续性存疑')
        elif not price_up and not vol_expand:
            return VolumePriceQuadrant('缩量下跌', 'orange', '价跌量缩，空头力量有限，可能为正常回调')
        else:
            return VolumePriceQuadrant('放量下跌', 'red', '价跌量增，空头主动打压，危险信号')

    # --- Section 6: Key Levels ---
    def calc_key_levels(self, latest: pd.Series, df: pd.DataFrame) -> Tuple[List[KeyLevel], List[KeyLevel]]:
        close = latest['close']
        levels = []

        for ma_name, ma_val in [('MA20', latest.get('ma20')), ('MA60', latest.get('ma60')), ('MA250', latest.get('ma250'))]:
            if ma_val is not None and not np.isnan(ma_val):
                lt = 'support' if ma_val < close else 'resistance'
                strength = '强' if ma_name == 'MA250' else '中'
                levels.append(KeyLevel(price=round(ma_val, 2), source=ma_name, level_type=lt, strength=strength))

        # 20-day high/low
        r20 = df.tail(20)
        levels.append(KeyLevel(price=round(r20['high'].max(), 2), source='20日高点', level_type='resistance', strength='中'))
        levels.append(KeyLevel(price=round(r20['low'].min(), 2), source='20日低点', level_type='support', strength='中'))

        # Integer levels (A-share psychological)
        for step in [5, 10]:
            nearest_up = int(close / step + 1) * step
            nearest_down = int(close / step) * step
            if nearest_up > close + step * 0.1:
                levels.append(KeyLevel(price=float(nearest_up), source=f'整数关口({step}元)', level_type='resistance', strength='弱'))
            if nearest_down < close - step * 0.1:
                levels.append(KeyLevel(price=float(nearest_down), source=f'整数关口({step}元)', level_type='support', strength='弱'))

        supports = sorted([l for l in levels if l.level_type == 'support'], key=lambda x: x.price, reverse=True)[:3]
        resistances = sorted([l for l in levels if l.level_type == 'resistance'], key=lambda x: x.price)[:3]
        return supports, resistances

    # --- Danger / Opportunity Signals ---
    def detect_alerts(self, latest: pd.Series, divergence: dict, kdj_signals: list) -> List[AlertSignal]:
        alerts = []
        close = latest['close']
        vr = latest.get('volume_ratio', 0)
        ma20 = latest.get('ma20')
        ma60 = latest.get('ma60')
        j = latest.get('kdj_j')
        rsi = latest.get('rsi')
        ma250 = latest.get('ma250')

        # Danger signals
        if ma20 is not None and not np.isnan(ma20) and close < ma20 and vr > 1.5:
            alerts.append(AlertSignal('danger', 'high', '放量跌破MA20', '趋势明显转弱，建议减仓'))
        if ma60 is not None and not np.isnan(ma60) and close < ma60 and vr > 1.5:
            alerts.append(AlertSignal('danger', 'critical', '放量跌破MA60', '中期趋势破坏，强烈建议减仓'))
        if divergence.get('type') == '顶背驰':
            alerts.append(AlertSignal('danger', 'medium', 'MACD顶背驰', divergence['description']))

        # KDJ danger: death cross in overbought
        if j is not None and not np.isnan(j) and j > 80:
            for s in kdj_signals:
                if s.name == 'KDJ死叉':
                    alerts.append(AlertSignal('danger', 'medium', 'KDJ超买区死叉', '短期回调信号'))

        # Opportunity signals
        if divergence.get('type') == '底背驰':
            alerts.append(AlertSignal('opportunity', 'medium', 'MACD底背驰', divergence['description']))
        if j is not None and not np.isnan(j) and j < 20:
            for s in kdj_signals:
                if s.name == 'KDJ金叉':
                    alerts.append(AlertSignal('opportunity', 'medium', 'KDJ超卖区金叉', '短期反弹信号'))
        if rsi is not None and not np.isnan(rsi) and rsi < 30:
            alerts.append(AlertSignal('opportunity', 'medium', 'RSI超卖', '存在技术性反弹机会（需结合其他指标）'))
        if ma250 is not None and not np.isnan(ma250) and abs(close - ma250) / ma250 < 0.03:
            alerts.append(AlertSignal('opportunity', 'medium', '年线支撑', '价格接近MA250支撑，关注是否有效企稳'))

        return alerts

    # --- Text Interpretations ---
    def interpret_rsi(self, rsi: float) -> dict:
        if rsi >= 80: return {'zone': '严重超买区', 'color': 'red', 'desc': f'RSI {rsi:.1f} 超过80，处于严重超买区间，回调风险极高，建议减仓'}
        if rsi >= 70: return {'zone': '超买区', 'color': 'orange', 'desc': f'RSI {rsi:.1f} 超过70，进入超买区间，上涨动能可能减弱'}
        if rsi >= 50: return {'zone': '强势区', 'color': 'green', 'desc': f'RSI {rsi:.1f} 位于50-70健康强势区间，趋势偏多'}
        if rsi >= 40: return {'zone': '中性区', 'color': 'gray', 'desc': f'RSI {rsi:.1f} 位于40-50区间，多空均衡偏弱'}
        if rsi >= 30: return {'zone': '偏弱区', 'color': 'orange', 'desc': f'RSI {rsi:.1f} 位于30-40弱势区间，需警惕继续下行'}
        return {'zone': '超卖区', 'color': 'green', 'desc': f'RSI {rsi:.1f} 低于30，进入超卖区间，存在技术性反弹机会'}

    def interpret_macd(self, latest: pd.Series) -> dict:
        dif = latest.get('macd_dif', 0)
        dea = latest.get('macd_dea', 0)
        hist = latest.get('macd_hist', 0)
        prev_hist = latest.get('prev_macd_hist', 0)

        if dif > 0 and dif > dea:
            status = '强势多头区，动量强'
        elif dif > 0 and dif < dea:
            status = '多头区死叉，动量减弱，注意顶背驰'
        elif dif < 0 and dif > dea:
            status = '熊区金叉，弱势反弹，需观察持续性'
        else:
            status = '弱势空头区，动量向下'

        # Histogram trend
        if hist > 0 and hist > prev_hist:
            hist_trend = '红柱放大'
        elif hist > 0 and hist <= prev_hist:
            hist_trend = '红柱收缩'
        elif hist < 0 and hist < prev_hist:
            hist_trend = '绿柱放大'
        elif hist < 0 and hist >= prev_hist:
            hist_trend = '绿柱收缩'
        else:
            hist_trend = '由负转正' if prev_hist < 0 and hist >= 0 else '由正转负'

        return {
            'dif': dif, 'dea': dea, 'hist': hist,
            'status': status, 'hist_trend': hist_trend,
            'hist_color': 'red' if hist >= 0 else 'green'
        }

    def interpret_kdj(self, latest: pd.Series) -> dict:
        k = latest.get('kdj_k')
        d = latest.get('kdj_d')
        j = latest.get('kdj_j')
        if any(v is None or pd.isna(v) for v in [k, d, j]):
            return {'k': None, 'd': None, 'j': None, 'status': '数据不足', 'desc': ''}

        if k > d and k > 50:
            status = '金叉区间，偏强势'
        elif k < d and k < 50:
            status = '死叉区间，偏弱势'
        elif k > d:
            status = '金叉区间，J值偏低' if j < 50 else '金叉区间'
        else:
            status = '死叉区间' + ('，J值偏高' if j > 70 else '')

        if j > 90:
            zone = '严重超买'
        elif j > 80:
            zone = '超买'
        elif j < 10:
            zone = '严重超卖'
        elif j < 20:
            zone = '超卖'
        else:
            zone = '中性'

        desc = f'KDJ 处于{status}，J值{j:.1f}处于{zone}区间'
        return {'k': k, 'd': d, 'j': j, 'status': status, 'zone': zone, 'desc': desc}

    def interpret_boll(self, latest: pd.Series) -> dict:
        upper = latest.get('boll_upper')
        middle = latest.get('boll_middle')
        lower = latest.get('boll_lower')
        pctb = latest.get('boll_pctb')
        bandwidth = latest.get('boll_bandwidth')

        if any(v is None or pd.isna(v) for v in [upper, middle, lower, pctb, bandwidth]):
            return None

        if pctb > 1.0:
            position = '突破上轨'
            pos_desc = '价格突破布林上轨，极度超买'
        elif pctb > 0.8:
            position = '上轨附近'
            pos_desc = '价格接近布林上轨，注意压力'
        elif pctb > 0.5:
            position = '上半区'
            pos_desc = '价格在中轨上方，偏多'
        elif pctb > 0.2:
            position = '下半区'
            pos_desc = '价格在中轨下方，偏空'
        elif pctb > 0:
            position = '下轨附近'
            pos_desc = '价格接近布林下轨，注意支撑'
        else:
            position = '突破下轨'
            pos_desc = '价格跌破布林下轨，极度超卖'

        if bandwidth < 0.05:
            width_signal = '布林带收口（带宽<5%），震荡格局，即将变盘'
        elif bandwidth > 0.2:
            width_signal = '布林带扩张（带宽>20%），趋势行情中'
        else:
            width_signal = f'布林带正常展开（带宽{bandwidth*100:.1f}%）'

        return {
            'upper': upper, 'middle': middle, 'lower': lower,
            'pctb': pctb, 'bandwidth': bandwidth,
            'position': position, 'pos_desc': pos_desc,
            'width_signal': width_signal
        }

    # --- Recent pattern analysis ---
    def analyze_recent_pattern(self, df: pd.DataFrame, n: int = 10) -> list:
        """Analyze recent N days pattern features."""
        recent = df.tail(n)
        if len(recent) < 2:
            return []

        features = []
        pct_changes = recent['pct_change'].values

        # Streak
        streak = 1
        for i in range(len(pct_changes) - 1, 0, -1):
            if (pct_changes[i] > 0) == (pct_changes[i-1] > 0):
                streak += 1
            else:
                break
        last_dir = 'up' if pct_changes[-1] > 0 else 'down'
        if streak >= 3:
            features.append(f"近{streak}日{'连涨' if last_dir == 'up' else '连跌'}")

        # Stats
        up_days = sum(1 for p in pct_changes if p > 0)
        down_days = sum(1 for p in pct_changes if p < 0)
        features.append(f"{up_days}涨{down_days}跌")

        # Max single day move
        max_up = max(pct_changes)
        max_down = min(pct_changes)
        if max_up > 5:
            features.append(f"最大单日涨幅{max_up:.1f}%")
        if max_down < -5:
            features.append(f"最大单日跌幅{abs(max_down):.1f}%")

        return features
```

**Step 2: Smoke test**

Run: `DB_ENV=online python -c "
from strategist.tech_scan.data_fetcher import DataFetcher
from strategist.tech_scan.indicator_calculator import IndicatorCalculator
from strategist.tech_scan.report_engine import ReportEngine

f = DataFetcher(env='online')
df = f.fetch_daily_data(['688386.SH'], lookback_days=300)
c = IndicatorCalculator()
df = c.calculate_all(df)
latest = df.iloc[-1]

e = ReportEngine()
score = e.calc_score(latest)
print(f'Score: {score.score}/10 - {score.trend_label}')
print(f'Advice: {score.action_advice}')

pattern = e.classify_ma_pattern(latest)
print(f'MA Pattern: {pattern.name} - {pattern.description}')

vp = e.analyze_volume_price(latest)
print(f'Vol-Price: {vp.label} - {vp.description}')
"`
Expected: Score 0-10, MA pattern, volume-price quadrant printed.

**Step 3: Commit**

```bash
git add strategist/tech_scan/report_engine.py
git commit -m "feat(tech-scan): add ReportEngine with scoring, interpretation, and analysis"
```

---

### Task 4: Rewrite single_scanner.py HTML Report (v2.0)

**Files:**
- Modify: `strategist/tech_scan/single_scanner.py`

This is the largest task. Replace `_generate_html_report()` with v2.0 layout:

**Step 1: Import ReportEngine and add to scan() method**

In `scan()`, after computing indicators, invoke:
```python
from strategist.tech_scan.report_engine import ReportEngine
engine = ReportEngine()
score_result = engine.calc_score(latest)
ma_pattern = engine.classify_ma_pattern(latest)
macd_interp = engine.interpret_macd(latest)
rsi_interp = engine.interpret_rsi(latest['rsi']) if latest.get('rsi') else None
kdj_interp = engine.interpret_kdj(latest)
boll_interp = engine.interpret_boll(latest)
vp_quadrant = engine.analyze_volume_price(latest)
supports, resistances = engine.calc_key_levels(latest, df)
divergence = self.detector.detect_macd_divergence(df) if len(df) >= 20 else {'type': '无背驰', 'confidence': '低', 'description': '数据不足'}
kdj_signals = self.detector.detect_kdj_signals(latest)
alerts = engine.detect_alerts(latest, divergence, kdj_signals)
recent_features = engine.analyze_recent_pattern(df)
```

**Step 2: Rewrite `_generate_html_report()` with v2.0 sections**

New section layout:
- Section 0: Header (code, name, date, data quality)
- Section 1: Comprehensive Conclusion (score bar, trend label, action advice, risk alerts)
- Section 2: Trend Analysis (MA table with interpretation, MA pattern badge, K-line chart)
- Section 3: Momentum (MACD with divergence, KDJ)
- Section 4: Overbought/Oversold (RSI with zone indicator, BOLL)
- Section 5: Volume-Price (volume ratio, turnover rate, quadrant analysis)
- Section 6: Key Levels (supports/resistances table, stop-loss)
- Section 7: Recent 10 Days (table with pattern features)

**Step 3: Add CSS for new components**

New CSS classes needed:
```css
.score-bar { height: 24px; border-radius: 12px; background: linear-gradient(to right, #e74c3c, #f1c40f, #27ae60); position: relative; }
.score-marker { position: absolute; top: -4px; width: 4px; height: 32px; background: #2c3e50; border-radius: 2px; }
.badge { display: inline-block; padding: 4px 12px; border-radius: 12px; color: white; font-weight: bold; font-size: 14px; }
.danger-alert { border-left: 4px solid #e74c3c; background: #ffeaea; padding: 8px 12px; margin: 4px 0; border-radius: 4px; }
.opportunity-alert { border-left: 4px solid #27ae60; background: #eafaf1; padding: 8px 12px; margin: 4px 0; border-radius: 4px; }
.rsi-zone-bar { height: 20px; border-radius: 4px; position: relative; background: linear-gradient(to right, #27ae60 0%, #27ae60 30%, #95a5a6 30%, #95a5a6 40%, #2ecc71 40%, #2ecc71 50%, #2ecc71 50%, #2ecc71 70%, #f39c12 70%, #f39c12 80%, #e74c3c 80%); }
.quadrant-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; }
.quadrant-cell { padding: 8px; text-align: center; border-radius: 4px; font-size: 12px; }
```

**Step 4: Full integration test**

Run: `DB_ENV=online python -m strategist.tech_scan.single_scanner --stock 688386 --chart`
Expected: HTML file with all 8 sections, score bar, badge, alerts, no errors.

**Step 5: Commit**

```bash
git add strategist/tech_scan/single_scanner.py
git commit -m "feat(tech-scan): rewrite HTML report v2.0 with scoring and interpretations"
```

---

### Task 5: Update Chart with BOLL Bands

**Files:**
- Modify: `strategist/tech_scan/chart_generator.py`

**Step 1: Add BOLL overlay to price panel**

In `generate_chart()`, after MA lines, add BOLL bands:
```python
# BOLL bands (if available)
if 'boll_upper' in df.columns:
    ax_price.plot(df.index[-display_n:], df['boll_upper'].values[-display_n:],
                  color='#95a5a6', linewidth=0.8, linestyle='--', alpha=0.7)
    ax_price.plot(df.index[-display_n:], df['boll_middle'].values[-display_n:],
                  color='#bdc3c7', linewidth=0.8, linestyle=':', alpha=0.5)
    ax_price.plot(df.index[-display_n:], df['boll_lower'].values[-display_n:],
                  color='#95a5a6', linewidth=0.8, linestyle='--', alpha=0.7)
```

**Step 2: Test chart generation**

Run: `DB_ENV=online python -m strategist.tech_scan.single_scanner --stock 688386 --chart`
Expected: Chart shows BOLL upper/middle/lower as dashed lines.

**Step 3: Commit**

```bash
git add strategist/tech_scan/chart_generator.py
git commit -m "feat(tech-scan): add BOLL bands to K-line chart"
```

---

### Task 6: Update SKILL.md and Final Validation

**Files:**
- Modify: `/Users/zhaobo/data0/person/mySkills/stock-tech-scan/SKILL.md`
- Copy to: `/Users/zhaobo/.claude/skills/stock-tech-scan/SKILL.md`

**Step 1: Update SKILL.md**

Add to "What It Does" section:
- Comprehensive scoring system (0-10)
- MACD divergence detection
- KDJ and BOLL indicators
- Volume-price quadrant analysis
- Danger/opportunity alert system

**Step 2: Final end-to-end test with multiple stocks**

Run on 2-3 different stocks to validate:
```bash
DB_ENV=online python -m strategist.tech_scan.single_scanner --stock 688386 --chart
DB_ENV=online python -m strategist.tech_scan.single_scanner --stock 600519 --chart
DB_ENV=online python -m strategist.tech_scan.single_scanner --stock 159915 --chart  # ETF
```

**Step 3: Commit everything**

```bash
git add -A
git commit -m "feat(tech-scan): v2.0 report with scoring, KDJ, BOLL, divergence"
```
