# -*- coding: utf-8 -*-
"""
市场状态分类器 - 多尺度综合判定 + 突变警报 + 冷却期
"""
import logging
from datetime import date
from typing import Optional, Tuple, Dict

import pandas as pd
import numpy as np

from .config import SVDMonitorConfig
from .schemas import MarketRegime

logger = logging.getLogger(__name__)


class MutationTracker:
    """突变状态追踪器 (带冷却期)"""

    def __init__(self, config: SVDMonitorConfig):
        self.config = config
        self._active = False
        self._trigger_count = 0

    def update(self, is_triggered: bool) -> bool:
        """
        更新突变状态，考虑冷却期逻辑

        Args:
            is_triggered: 本次是否检测到突变信号

        Returns:
            当前是否应使用突变权重
        """
        if is_triggered:
            self._active = True
            self._trigger_count += 1
            return True

        if self._active:
            self._trigger_count += 1
            if self._trigger_count < self.config.mutation_cooldown_days:
                return True
            else:
                self._active = False
                self._trigger_count = 0
                return False

        return False

    @property
    def is_active(self) -> bool:
        return self._active

    def reset(self):
        self._active = False
        self._trigger_count = 0


class RegimeClassifier:
    """市场状态分类器"""

    def __init__(self, config: SVDMonitorConfig = None):
        self.config = config or SVDMonitorConfig()
        self.mutation_tracker = MutationTracker(self.config)

    def detect_mutation(self, f1_short: float, f1_long: float,
                        long_history: pd.Series) -> Tuple[bool, float]:
        """
        突变检测: 短窗口 F1 偏离长窗口历史分布 2σ 以上
        """
        if len(long_history) < 10:
            return False, 0.0

        hist_mean = long_history.mean()
        hist_std = long_history.std()

        if hist_std < 1e-8:
            return False, 0.0

        deviation = (f1_short - hist_mean) / hist_std

        if abs(deviation) > self.config.mutation_sigma_trigger:
            return True, abs(deviation)

        return False, abs(deviation)

    def classify(self, results_df: pd.DataFrame, calc_date: date) -> MarketRegime:
        """
        多尺度综合判定市场状态
        """
        f1_values = {}
        for ws in self.config.windows.keys():
            subset = results_df[
                (results_df['window_size'] == ws) &
                (results_df['calc_date'] == calc_date)
            ]
            if len(subset) > 0:
                f1_values[ws] = subset['top1_var_ratio'].iloc[-1]

        f1_short = f1_values.get(20)
        f1_mid = f1_values.get(60)
        f1_long = f1_values.get(120)

        available_windows = [w for w in [20, 60, 120] if f1_values.get(w) is not None]

        if not available_windows:
            return MarketRegime(
                calc_date=calc_date,
                market_state="数据不足",
                is_mutation=False,
                final_score=0.0,
                weights_used={},
            )

        # 突变检测
        is_mutation = False
        if f1_short is not None and f1_long is not None:
            long_hist = results_df[
                (results_df['window_size'] == 120) &
                (results_df['calc_date'] < calc_date)
            ]['top1_var_ratio']

            if len(long_hist) >= 10:
                triggered, deviation = self.detect_mutation(f1_short, f1_long, long_hist)
                is_mutation = self.mutation_tracker.update(triggered)
                if triggered:
                    logger.info(f"突变信号: deviation={deviation:.2f}σ, active={is_mutation}")

        # 动态权重分配
        weights = self.config.base_weights.copy()
        if is_mutation:
            weights = self.config.mutation_weights.copy()

        # 加权得分
        final_score = 0.0
        weight_sum = 0.0
        for ws in [20, 60, 120]:
            if f1_values.get(ws) is not None and ws in weights:
                final_score += f1_values[ws] * weights[ws]
                weight_sum += weights[ws]

        if weight_sum > 0:
            final_score /= weight_sum

        # 状态判定
        if final_score > self.config.state_threshold_high:
            state = "齐涨齐跌"
        elif final_score > self.config.state_threshold_low:
            state = "板块分化"
        else:
            state = "个股行情"

        return MarketRegime(
            calc_date=calc_date,
            market_state=state,
            is_mutation=is_mutation,
            final_score=round(final_score, 4),
            f1_short=round(f1_short, 4) if f1_short is not None else None,
            f1_mid=round(f1_mid, 4) if f1_mid is not None else None,
            f1_long=round(f1_long, 4) if f1_long is not None else None,
            weights_used=weights,
        )

    def reset_mutation(self):
        """重置突变追踪器"""
        self.mutation_tracker.reset()
