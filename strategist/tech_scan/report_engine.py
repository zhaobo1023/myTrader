# -*- coding: utf-8 -*-
"""
Report engine for tech scan v2.0 - scoring, interpretation, and structured analysis.
"""
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

        # MA alignment bonus/penalty
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

        if score >= 8.0: label, advice = '强势多头', '积极持有，可适当加仓'
        elif score >= 6.0: label, advice = '偏多', '持有为主，轻仓参与'
        elif score >= 4.0: label, advice = '中性震荡', '观望为主，等待方向明确'
        elif score >= 2.0: label, advice = '偏空', '减仓或空仓，警惕破位'
        else: label, advice = '强势空头', '空仓，严控风险'

        return ScoreResult(score=score, trend_label=label, action_advice=advice)

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

    def calc_key_levels(self, latest: pd.Series, df: pd.DataFrame) -> Tuple[List[KeyLevel], List[KeyLevel]]:
        close = latest['close']
        levels = []
        for ma_name, ma_val in [('MA20', latest.get('ma20')), ('MA60', latest.get('ma60')), ('MA250', latest.get('ma250'))]:
            if ma_val is not None and not np.isnan(ma_val):
                lt = 'support' if ma_val < close else 'resistance'
                strength = '强' if ma_name == 'MA250' else '中'
                levels.append(KeyLevel(price=round(ma_val, 2), source=ma_name, level_type=lt, strength=strength))
        r20 = df.tail(20)
        levels.append(KeyLevel(price=round(r20['high'].max(), 2), source='20日高点', level_type='resistance', strength='中'))
        levels.append(KeyLevel(price=round(r20['low'].min(), 2), source='20日低点', level_type='support', strength='中'))
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

    def detect_alerts(self, latest: pd.Series, divergence: dict, kdj_signals: list) -> List[AlertSignal]:
        alerts = []
        close = latest['close']
        vr = latest.get('volume_ratio', 0)
        ma20 = latest.get('ma20')
        ma60 = latest.get('ma60')
        j = latest.get('kdj_j')
        rsi = latest.get('rsi')
        ma250 = latest.get('ma250')
        if ma20 is not None and not np.isnan(ma20) and close < ma20 and vr > 1.5:
            alerts.append(AlertSignal('danger', 'high', '放量跌破MA20', '趋势明显转弱，建议减仓'))
        if ma60 is not None and not np.isnan(ma60) and close < ma60 and vr > 1.5:
            alerts.append(AlertSignal('danger', 'critical', '放量跌破MA60', '中期趋势破坏，强烈建议减仓'))
        if divergence.get('type') == '顶背驰':
            alerts.append(AlertSignal('danger', 'medium', 'MACD顶背驰', divergence['description']))
        if j is not None and not np.isnan(j) and j > 80:
            for s in kdj_signals:
                if s.name == 'KDJ死叉':
                    alerts.append(AlertSignal('danger', 'medium', 'KDJ超买区死叉', '短期回调信号'))
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
        return {'dif': dif, 'dea': dea, 'hist': hist, 'status': status, 'hist_trend': hist_trend, 'hist_color': 'red' if hist >= 0 else 'green'}

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
        return {'upper': upper, 'middle': middle, 'lower': lower, 'pctb': pctb, 'bandwidth': bandwidth, 'position': position, 'pos_desc': pos_desc, 'width_signal': width_signal}

    def analyze_recent_pattern(self, df: pd.DataFrame, n: int = 10) -> list:
        recent = df.tail(n)
        if len(recent) < 2:
            return []
        features = []
        pct_changes = recent['pct_change'].values
        streak = 1
        for i in range(len(pct_changes) - 1, 0, -1):
            if (pct_changes[i] > 0) == (pct_changes[i-1] > 0):
                streak += 1
            else:
                break
        last_dir = 'up' if pct_changes[-1] > 0 else 'down'
        if streak >= 3:
            features.append(f"近{streak}日{'连涨' if last_dir == 'up' else '连跌'}")
        up_days = sum(1 for p in pct_changes if p > 0)
        down_days = sum(1 for p in pct_changes if p < 0)
        features.append(f"{up_days}涨{down_days}跌")
        max_up = max(pct_changes)
        max_down = min(pct_changes)
        if max_up > 5:
            features.append(f"最大单日涨幅{max_up:.1f}%")
        if max_down < -5:
            features.append(f"最大单日跌幅{abs(max_down):.1f}%")
        return features
