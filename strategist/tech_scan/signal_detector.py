# -*- coding: utf-8 -*-
"""
信号检测器

检测技术面预警信号：回踩、突破、金叉/死叉、背离、缩量回调、RPS拐点等。
支持信号分级（警示 vs 破位）和组合信号。
"""
import pandas as pd
import numpy as np
from typing import List, Dict, Set
from dataclasses import dataclass
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class SignalLevel(Enum):
    """信号级别"""
    RED = "🔴"      # 红灯：需要关注
    YELLOW = "⚠️"   # 黄灯：提醒
    GREEN = "🟢"    # 绿灯：积极信号
    INFO = "📊"     # 信息


class SignalSeverity(Enum):
    """信号严重程度（用于红灯内部分级）"""
    WARNING = "警示"     # 软信号，趋势未确认反转
    BREAKDOWN = "破位"   # 硬信号，趋势可能已经反转


class SignalTag:
    """信号标签常量"""
    DIVERGENCE = "背离"
    OVERSOLD_BOUNCE = "超卖反弹"
    SHRINK_PULLBACK = "缩量回调"
    DANGER = "极度危险"
    RPS_INFLECTION_UP = "RPS底部启动"
    RPS_DECAY = "RPS强度衰减"


# 板块分类映射
SECTOR_MAP = {
    '煤炭': {'600188', '601225', '601898', '600863'},
    '有色金属': {'002738', '000408', '000792', '601899', '601600', '600547'},
    '银行': {'600015', '601398', '601288', '601939', '600036'},
    '电力设备': {'300274', '600406', '002895'},
    '消费': {'000858', '002241', '300760'},
    '房地产': {'601155'},
    '化工': {'600989'},
    '医药': {'159992'},
    '农业': {'159698'},
    '钢铁特材': {'002318'},
    '科技': {'000725', '300775', '601717', '159792'},
    '保险': {'601318'},
}


def get_sector(code: str) -> str:
    """根据股票代码获取板块分类"""
    code_num = code.split('.')[0]
    for sector, codes in SECTOR_MAP.items():
        if code_num in codes:
            return sector
    return '其他'


@dataclass
class Signal:
    """信号"""
    name: str
    level: SignalLevel
    description: str
    severity: SignalSeverity = SignalSeverity.WARNING
    tag: str = ""


class SignalDetector:
    """信号检测器"""

    def __init__(
        self,
        pullback_threshold: float = 0.015,
        volume_ratio_threshold: float = 1.5,
        shrink_volume_ratio: float = 0.7,
        rsi_overbought: int = 70,
        rsi_oversold: int = 30,
        rps_warning_threshold: int = 80,
        rps_slope_threshold: float = 1.5
    ):
        self.pullback_threshold = pullback_threshold
        self.volume_ratio_threshold = volume_ratio_threshold
        self.shrink_volume_ratio = shrink_volume_ratio
        self.rsi_overbought = rsi_overbought
        self.rsi_oversold = rsi_oversold
        self.rps_warning_threshold = rps_warning_threshold
        self.rps_slope_threshold = rps_slope_threshold

    def detect_all(self, row: pd.Series) -> List[Signal]:
        """检测所有信号（含组合信号）"""
        signals = []

        signals.extend(self._detect_ma_signals(row))
        signals.extend(self._detect_macd_signals(row))
        signals.extend(self._detect_rsi_signals(row))
        signals.extend(self._detect_rps_signals(row))
        signals.extend(self._detect_breakout_signals(row))
        signals.extend(self._detect_volume_signals(row))

        # 组合信号
        signals.extend(self._detect_composite_signals(row, signals))

        return signals

    def _detect_ma_signals(self, row: pd.Series) -> List[Signal]:
        """检测均线相关信号"""
        signals = []
        close = row.get('close')

        if close is None or pd.isna(close):
            return signals

        ma20 = row.get('ma20')
        if ma20 and not pd.isna(ma20):
            bias = abs(close / ma20 - 1)
            if bias < self.pullback_threshold:
                if close >= ma20:
                    signals.append(Signal(
                        name="回踩20日线",
                        level=SignalLevel.YELLOW,
                        description=f"收盘价距MA20仅{bias*100:.1f}%",
                        severity=SignalSeverity.WARNING
                    ))
                else:
                    signals.append(Signal(
                        name="跌破20日线",
                        level=SignalLevel.RED,
                        description=f"收盘价低于MA20 {bias*100:.1f}%",
                        severity=SignalSeverity.WARNING
                    ))

        ma60 = row.get('ma60')
        if ma60 and not pd.isna(ma60):
            bias = abs(close / ma60 - 1)
            if bias < self.pullback_threshold:
                if close >= ma60:
                    signals.append(Signal(
                        name="回踩60日线",
                        level=SignalLevel.YELLOW,
                        description=f"收盘价距MA60仅{bias*100:.1f}%",
                        severity=SignalSeverity.WARNING
                    ))
                else:
                    signals.append(Signal(
                        name="跌破60日线",
                        level=SignalLevel.RED,
                        description=f"收盘价低于MA60 {bias*100:.1f}%",
                        severity=SignalSeverity.WARNING
                    ))

        # MA5 上穿/下穿 MA20
        ma5 = row.get('ma5')
        prev_ma5 = row.get('prev_ma5')
        prev_ma20 = row.get('prev_ma20')

        if all(v is not None and not pd.isna(v) for v in [ma5, ma20, prev_ma5, prev_ma20]):
            if ma5 > ma20 and prev_ma5 <= prev_ma20:
                signals.append(Signal(
                    name="MA5金叉MA20",
                    level=SignalLevel.GREEN,
                    description="短期均线上穿中期均线",
                    severity=SignalSeverity.WARNING
                ))
            elif ma5 < ma20 and prev_ma5 >= prev_ma20:
                is_below_ma20 = close < ma20
                signals.append(Signal(
                    name="MA5死叉MA20",
                    level=SignalLevel.RED,
                    description="短期均线下穿中期均线" + ("，价格已跌破MA20" if is_below_ma20 else ""),
                    severity=SignalSeverity.BREAKDOWN if is_below_ma20 else SignalSeverity.WARNING
                ))

        return signals

    def _detect_macd_signals(self, row: pd.Series) -> List[Signal]:
        """检测 MACD 信号"""
        signals = []

        dif = row.get('macd_dif')
        dea = row.get('macd_dea')
        prev_dif = row.get('prev_macd_dif')
        prev_dea = row.get('prev_macd_dea')

        if all(v is not None and not pd.isna(v) for v in [dif, dea, prev_dif, prev_dea]):
            if dif > dea and prev_dif <= prev_dea:
                signals.append(Signal(
                    name="MACD金叉",
                    level=SignalLevel.GREEN,
                    description="DIF上穿DEA",
                    severity=SignalSeverity.WARNING
                ))
            elif dif < dea and prev_dif >= prev_dea:
                signals.append(Signal(
                    name="MACD死叉",
                    level=SignalLevel.RED,
                    description="DIF下穿DEA",
                    severity=SignalSeverity.WARNING
                ))

        return signals

    def _detect_rsi_signals(self, row: pd.Series) -> List[Signal]:
        """检测 RSI 信号"""
        signals = []

        rsi = row.get('rsi')
        if rsi is not None and not pd.isna(rsi):
            if rsi > self.rsi_overbought:
                signals.append(Signal(
                    name="RSI超买",
                    level=SignalLevel.YELLOW,
                    description=f"RSI={rsi:.1f} > {self.rsi_overbought}",
                    severity=SignalSeverity.WARNING
                ))
            elif rsi < self.rsi_oversold:
                if rsi < 20:
                    signals.append(Signal(
                        name="RSI严重超卖",
                        level=SignalLevel.YELLOW,
                        description=f"RSI={rsi:.1f}，严重超卖不宜盲目杀跌",
                        severity=SignalSeverity.WARNING,
                        tag=SignalTag.OVERSOLD_BOUNCE
                    ))
                else:
                    signals.append(Signal(
                        name="RSI超卖",
                        level=SignalLevel.YELLOW,
                        description=f"RSI={rsi:.1f} < {self.rsi_oversold}",
                        severity=SignalSeverity.WARNING,
                        tag=SignalTag.OVERSOLD_BOUNCE
                    ))

        return signals

    def _detect_rps_signals(self, row: pd.Series) -> List[Signal]:
        """检测 RPS 信号"""
        signals = []

        for col in ['rps_250', 'rps', 'rps_120']:
            rps = row.get(col)
            if rps is not None and not pd.isna(rps):
                if rps < self.rps_warning_threshold:
                    signals.append(Signal(
                        name="RPS走弱",
                        level=SignalLevel.RED,
                        description=f"RPS={rps:.0f} < {self.rps_warning_threshold}",
                        severity=SignalSeverity.WARNING
                    ))
                elif rps >= 90:
                    signals.append(Signal(
                        name="RPS强势",
                        level=SignalLevel.GREEN,
                        description=f"RPS={rps:.0f} >= 90",
                        severity=SignalSeverity.WARNING
                    ))
                break

        # RPS slope 信号
        slope = row.get('rps_slope')
        if slope is not None and not pd.isna(slope):
            if slope > self.rps_slope_threshold:
                signals.append(Signal(
                    name="RPS快速拉升",
                    level=SignalLevel.GREEN,
                    description=f"RPS斜率Z={slope:.2f}",
                    severity=SignalSeverity.WARNING
                ))
            elif slope < -self.rps_slope_threshold:
                signals.append(Signal(
                    name="RPS快速下滑",
                    level=SignalLevel.RED,
                    description=f"RPS斜率Z={slope:.2f}",
                    severity=SignalSeverity.WARNING
                ))

        return signals

    def _detect_breakout_signals(self, row: pd.Series) -> List[Signal]:
        """检测突破信号"""
        signals = []

        close = row.get('close')
        high_20 = row.get('high_20')

        if close is not None and high_20 is not None:
            if not pd.isna(close) and not pd.isna(high_20):
                if close >= high_20:
                    signals.append(Signal(
                        name="创20日新高",
                        level=SignalLevel.GREEN,
                        description=f"收盘价={close:.2f} >= 20日高点",
                        severity=SignalSeverity.WARNING
                    ))

        return signals

    def _detect_volume_signals(self, row: pd.Series) -> List[Signal]:
        """检测量价信号"""
        signals = []

        volume_ratio = row.get('volume_ratio')
        if volume_ratio is not None and not pd.isna(volume_ratio):
            if volume_ratio >= self.volume_ratio_threshold:
                signals.append(Signal(
                    name="放量",
                    level=SignalLevel.INFO,
                    description=f"成交量是5日均量的{volume_ratio:.1f}倍",
                    severity=SignalSeverity.WARNING
                ))

        return signals

    def _detect_composite_signals(self, row: pd.Series, base_signals: List[Signal]) -> List[Signal]:
        """
        组合信号检测

        1. 背离：价格破位 + MACD金叉 → 潜在筑底
        2. 缩量回调：价格跌 + 量缩 → 降级
        3. RPS拐点：RPS高但斜率转负 → 强度衰减
        """
        composite = []
        signal_names = {s.name for s in base_signals}

        # 1. 背离：价格破位 + MACD 金叉
        price_breakdown = signal_names & {'跌破20日线', '跌破60日线'}
        has_macd_golden = 'MACD金叉' in signal_names

        if price_breakdown and has_macd_golden:
            composite.append(Signal(
                name="底背离信号",
                level=SignalLevel.YELLOW,
                description="价格跌破均线但MACD金叉，指标与价格背离，可能筑底",
                severity=SignalSeverity.WARNING,
                tag=SignalTag.DIVERGENCE
            ))

        # 2. 缩量回调：今日下跌 + 成交量 < 0.7x 均量
        pct_change = row.get('pct_change')
        volume_ratio = row.get('volume_ratio')
        if (pct_change is not None and not pd.isna(pct_change) and pct_change < 0
                and volume_ratio is not None and not pd.isna(volume_ratio)
                and volume_ratio < self.shrink_volume_ratio):
            composite.append(Signal(
                name="缩量回调",
                level=SignalLevel.YELLOW,
                description=f"下跌{pct_change:.1f}%但量比仅{volume_ratio:.1f}x，缩量回踩暂无恐慌抛售",
                severity=SignalSeverity.WARNING,
                tag=SignalTag.SHRINK_PULLBACK
            ))

        # 3. RPS 强度衰减：RPS >= 90 但斜率转负
        rps = row.get('rps_250') or row.get('rps')
        slope = row.get('rps_slope')
        if (rps is not None and not pd.isna(rps) and rps >= 90
                and slope is not None and not pd.isna(slope) and slope < -0.5):
            composite.append(Signal(
                name="RPS强度衰减",
                level=SignalLevel.YELLOW,
                description=f"RPS={rps:.0f}仍强势但斜率Z={slope:.2f}转负，注意落袋",
                severity=SignalSeverity.WARNING,
                tag=SignalTag.RPS_DECAY
            ))

        return composite

    def get_trend_status(self, row: pd.Series) -> str:
        """判断趋势状态"""
        ma5 = row.get('ma5')
        ma20 = row.get('ma20')
        ma60 = row.get('ma60')
        ma250 = row.get('ma250')

        values = [ma5, ma20, ma60]
        if any(v is None or pd.isna(v) for v in values):
            return "数据不足"

        if ma5 > ma20 > ma60:
            if ma250 is not None and not pd.isna(ma250) and ma60 > ma250:
                return "强势多头"
            return "多头排列"

        if ma5 < ma20 < ma60:
            if ma250 is not None and not pd.isna(ma250) and ma60 < ma250:
                return "强势空头"
            return "空头排列"

        return "震荡整理"

    @staticmethod
    def detect_sector_alerts(red_codes: List[str]) -> List[Dict]:
        """板块联动预警（>= 2只红灯触发）"""
        sector_codes: Dict[str, List[str]] = {}
        for code in red_codes:
            sector = get_sector(code)
            sector_codes.setdefault(sector, []).append(code)

        alerts = []
        for sector, codes in sector_codes.items():
            if sector != '其他' and len(codes) >= 2:
                alerts.append({
                    'sector': sector,
                    'codes': codes,
                    'count': len(codes)
                })

        alerts.sort(key=lambda x: x['count'], reverse=True)
        return alerts

    @staticmethod
    def detect_rps_slope_transition(analysis_results: List[Dict]) -> List[Dict]:
        """RPS 斜率强弱转换：RPS >= 80 但 Z < -1.0"""
        transitions = []
        for r in analysis_results:
            row = r.get('row')
            if row is None:
                continue
            rps = row.get('rps_250') or row.get('rps')
            slope = row.get('rps_slope')
            if rps is not None and not pd.isna(rps) and slope is not None and not pd.isna(slope):
                if rps >= 80 and slope < -1.0:
                    transitions.append({
                        'code': r['code'],
                        'name': r['name'],
                        'level': r['level'],
                        'rps': rps,
                        'slope': slope
                    })
        transitions.sort(key=lambda x: x['slope'])
        return transitions

    @staticmethod
    def calc_stop_loss_price(row: pd.Series, method: str = 'atr') -> Dict:
        """
        计算止损参考价

        Args:
            row: 包含技术指标的数据行
            method: 'atr' (2x ATR) 或 'ma20' (MA20 硬止损)

        Returns:
            {'stop_price': float, 'method': str, 'description': str}
        """
        close = row.get('close')
        if close is None or pd.isna(close):
            return {}

        if method == 'atr':
            atr = row.get('atr_14')
            if atr and not pd.isna(atr):
                stop_price = close - 2 * atr
                return {
                    'stop_price': round(stop_price, 2),
                    'method': 'ATR',
                    'description': f"收盘价 - 2*ATR(14) = {close:.2f} - {2*atr:.2f}"
                }
        elif method == 'ma20':
            ma20 = row.get('ma20')
            if ma20 and not pd.isna(ma20):
                return {
                    'stop_price': round(ma20, 2),
                    'method': 'MA20',
                    'description': f"MA20硬止损位 = {ma20:.2f}"
                }

        return {}

    @staticmethod
    def calc_divergence_target(row: pd.Series) -> Dict:
        """
        计算背离反弹目标位

        价格破位但MACD金叉时，反弹目标取 MA60，
        如果 MA60 不存在则取 MA20。

        Returns:
            {'target_price': float, 'target_ma': str, 'space_pct': float}
        """
        close = row.get('close')
        if close is None or pd.isna(close):
            return {}

        # 优先取 MA60
        ma60 = row.get('ma60')
        if ma60 and not pd.isna(ma60) and close < ma60:
            space = (ma60 / close - 1) * 100
            return {
                'target_price': round(ma60, 2),
                'target_ma': 'MA60',
                'space_pct': round(space, 1)
            }

        ma20 = row.get('ma20')
        if ma20 and not pd.isna(ma20) and close < ma20:
            space = (ma20 / close - 1) * 100
            return {
                'target_price': round(ma20, 2),
                'target_ma': 'MA20',
                'space_pct': round(space, 1)
            }

        return {}


def detect_signals(row: pd.Series) -> List[Signal]:
    """便捷函数：检测信号"""
    detector = SignalDetector()
    return detector.detect_all(row)
