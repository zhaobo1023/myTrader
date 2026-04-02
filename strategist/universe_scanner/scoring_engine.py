# -*- coding: utf-8 -*-
"""
三层分层过滤 + 评分引擎

Pipeline:
  1. 海选池 (Universe)      - 剔除低流动性 + MA250 下方标的
  2. 动态关注池 (Watchlist)  - RPS > 80 + 趋势对齐 (MA20/60 上方)
  3. 核心监控池 (HighPriority) - 打分制，取 Top N

评分维度:
  +2  MACD 金叉 / 均线多头排列
  +2  热门行业
  +3  底背离 / RPS 创新高
  +1  放量突破 (量比 > 1.5)
  +1  RSI 超卖反弹区间 (30-50)
  -2  RSI 超买 (> 80)
  -1  缩量回调
"""
import pandas as pd
import numpy as np
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional

from .config import UniverseScanConfig

logger = logging.getLogger(__name__)


@dataclass
class StockScore:
    """单只股票评分结果"""
    code: str
    name: str
    industry: str
    close: float
    pct_change: float
    # 均线
    ma20: Optional[float] = None
    ma60: Optional[float] = None
    ma250: Optional[float] = None
    # RPS
    rps_120: Optional[float] = None
    rps_250: Optional[float] = None
    rps_slope: Optional[float] = None
    # 技术指标
    rsi: Optional[float] = None
    volume_ratio: Optional[float] = None
    macd_dif: Optional[float] = None
    macd_dea: Optional[float] = None
    macd_hist: Optional[float] = None
    prev_macd_dif: Optional[float] = None
    prev_macd_dea: Optional[float] = None
    ma5: Optional[float] = None
    # 成交额
    avg_amount_60d: Optional[float] = None
    # 趋势
    trend: str = ""
    # 评分
    total_score: int = 0
    score_details: List[str] = field(default_factory=list)
    # 分层
    tier: str = "universe"  # universe / watchlist / high_priority
    # 信号标签
    signals: List[str] = field(default_factory=list)


class ScoringEngine:
    """分层过滤 + 评分引擎"""

    def __init__(self, config: UniverseScanConfig = None):
        self.cfg = config or UniverseScanConfig()

    def run(self, df: pd.DataFrame) -> Dict[str, List[StockScore]]:
        """
        执行完整分层流水线

        Args:
            df: 最新一天的 DataFrame，需包含所有技术指标列

        Returns:
            {
                'universe': [...],      # 海选池（通过基础过滤的全部）
                'watchlist': [...],     # 动态关注池
                'high_priority': [...], # 核心监控池
                'filtered_out': [...],  # 被剔除的
                'hk_other': [...],      # 港股/其他（仅展示）
            }
        """
        results = {
            'universe': [],
            'watchlist': [],
            'high_priority': [],
            'filtered_out': [],
        }

        for _, row in df.iterrows():
            score = self._build_score(row)

            # Step 1: 海选过滤
            if not self._pass_universe_filter(score):
                results['filtered_out'].append(score)
                continue

            score.tier = 'universe'
            results['universe'].append(score)

            # Step 2: 动态关注池门槛
            if not self._pass_watchlist_filter(score):
                continue

            score.tier = 'watchlist'
            results['watchlist'].append(score)

        # Step 3: 对 watchlist 打分
        for score in results['watchlist']:
            self._calc_score(score)

        # Step 4: 排序取 Top N 进入核心监控池
        sorted_watchlist = sorted(
            results['watchlist'],
            key=lambda s: s.total_score,
            reverse=True,
        )
        results['high_priority'] = sorted_watchlist[:self.cfg.high_priority_top_n]
        for s in results['high_priority']:
            s.tier = 'high_priority'

        logger.info(f"分层结果: 海选池 {len(results['universe'])} | "
                     f"关注池 {len(results['watchlist'])} | "
                     f"核心池 {len(results['high_priority'])} | "
                     f"剔除 {len(results['filtered_out'])}")

        return results

    def _build_score(self, row: pd.Series) -> StockScore:
        """从 DataFrame row 构建 StockScore"""
        def safe_float(val, default=None):
            if val is None or (isinstance(val, float) and np.isnan(val)):
                return default
            return float(val)

        score = StockScore(
            code=row.get('stock_code', ''),
            name=row.get('stock_name', ''),
            industry=row.get('industry', ''),
            close=safe_float(row.get('close')),
            pct_change=safe_float(row.get('pct_change'), 0),
            ma20=safe_float(row.get('ma20')),
            ma60=safe_float(row.get('ma60')),
            ma250=safe_float(row.get('ma250')),
            rps_120=safe_float(row.get('rps_120')),
            rps_250=safe_float(row.get('rps_250')),
            rps_slope=safe_float(row.get('rps_slope')),
            rsi=safe_float(row.get('rsi')),
            volume_ratio=safe_float(row.get('volume_ratio')),
            macd_dif=safe_float(row.get('macd_dif')),
            macd_dea=safe_float(row.get('macd_dea')),
            macd_hist=safe_float(row.get('macd_hist')),
            prev_macd_dif=safe_float(row.get('prev_macd_dif')),
            prev_macd_dea=safe_float(row.get('prev_macd_dea')),
            ma5=safe_float(row.get('ma5')),
            avg_amount_60d=safe_float(row.get('avg_amount_60d')),
        )
        return score

    # ----------------------------------------------------------------
    # Step 1: 海选过滤
    # ----------------------------------------------------------------
    def _pass_universe_filter(self, s: StockScore) -> bool:
        """
        海选过滤（硬指标）:
        - 60日均成交额 >= 5000万
        - 价格在 MA250 上方（如果 MA250 存在）
        """
        # 流动性过滤
        if s.avg_amount_60d is not None and s.avg_amount_60d < self.cfg.min_avg_amount:
            return False

        # MA250 过滤
        if self.cfg.ma250_required and s.ma250 is not None:
            if s.close < s.ma250:
                return False

        return True

    # ----------------------------------------------------------------
    # Step 2: 动态关注池门槛
    # ----------------------------------------------------------------
    def _pass_watchlist_filter(self, s: StockScore) -> bool:
        """
        动态关注池门槛:
        - RPS(120) > 80 或 RPS(250) > 80
        - 价格在 MA20 或 MA60 之上
        """
        # RPS 过滤
        rps_120_ok = s.rps_120 is not None and s.rps_120 > self.cfg.rps_min
        rps_250_ok = s.rps_250 is not None and s.rps_250 > self.cfg.rps_min
        if not rps_120_ok and not rps_250_ok:
            return False

        # 趋势过滤: 价格至少在一条均线上方
        above_ma20 = s.ma20 is not None and s.close >= s.ma20
        above_ma60 = s.ma60 is not None and s.close >= s.ma60
        if not above_ma20 and not above_ma60:
            return False

        return True

    # ----------------------------------------------------------------
    # Step 3: 评分
    # ----------------------------------------------------------------
    def _calc_score(self, s: StockScore):
        """计算综合评分"""
        score = 0
        details = []
        signals = []

        # --- MACD 金叉 (+2) ---
        if (s.prev_macd_dif is not None and s.prev_macd_dea is not None
                and s.macd_dif is not None and s.macd_dea is not None):
            if s.macd_dif > s.macd_dea and s.prev_macd_dif <= s.prev_macd_dea:
                score += self.cfg.score_macd_golden_cross
                details.append(f"MACD金叉(+{self.cfg.score_macd_golden_cross})")
                signals.append("MACD金叉")

        # --- 均线多头排列 (+2) ---
        if s.ma5 and s.ma20 and s.ma60:
            if s.ma5 > s.ma20 > s.ma60:
                score += self.cfg.score_ma_bullish
                details.append(f"均线多头(+{self.cfg.score_ma_bullish})")
                signals.append("均线多头排列")
                s.trend = "多头排列"

        # --- 热门行业 (+2) ---
        if self._is_hot_industry(s.industry):
            score += self.cfg.score_hot_industry
            details.append(f"热门行业({s.industry})(+{self.cfg.score_hot_industry})")

        # --- 底背离 (+3) ---
        if self._has_divergence(s):
            score += self.cfg.score_divergence
            details.append(f"底背离(+{self.cfg.score_divergence})")
            signals.append("底背离信号")

        # --- RPS 创新高 (+3) ---
        rps_max = max(s.rps_120 or 0, s.rps_250 or 0)
        if rps_max >= self.cfg.rps_new_high_threshold:
            score += self.cfg.score_rps_new_high
            details.append(f"RPS新高({rps_max:.0f})(+{self.cfg.score_rps_new_high})")
            signals.append("RPS创新高")

        # --- 放量突破 (+1) ---
        if s.volume_ratio is not None and s.volume_ratio >= self.cfg.volume_ratio_threshold:
            score += self.cfg.score_volume_breakout
            details.append(f"放量({s.volume_ratio:.1f}x)(+{self.cfg.score_volume_breakout})")
            signals.append(f"放量{s.volume_ratio:.1f}x")

        # --- RSI 超卖反弹 (+1) ---
        if s.rsi is not None and self.cfg.rsi_oversold <= s.rsi <= 50:
            score += self.cfg.score_rsi_oversold_bounce
            details.append(f"RSI反弹区({s.rsi:.0f})(+{self.cfg.score_rsi_oversold_bounce})")

        # --- RSI 超买扣分 (-2) ---
        if s.rsi is not None and s.rsi > self.cfg.rsi_overbought:
            score += self.cfg.score_rsi_overbought
            details.append(f"RSI超买({s.rsi:.0f})({self.cfg.score_rsi_overbought})")
            signals.append("RSI超买")

        # --- 缩量回调 (-1) ---
        if (s.pct_change < 0
                and s.volume_ratio is not None
                and s.volume_ratio < 0.7):
            score += self.cfg.score_shrink_pullback
            details.append(f"缩量回调({self.cfg.score_shrink_pullback})")

        # --- RPS 斜率加分 ---
        if s.rps_slope is not None:
            if s.rps_slope > 1.5:
                score += 1
                details.append("RPS斜率强势(+1)")
                signals.append("RPS快速拉升")
            elif s.rps_slope < -1.5:
                score -= 1
                details.append("RPS斜率走弱(-1)")
                signals.append("RPS快速下滑")

        s.total_score = score
        s.score_details = details
        s.signals = signals

    def _is_hot_industry(self, industry: str) -> bool:
        """判断是否为热门行业"""
        if not industry or industry == '--':
            return False
        for kw in self.cfg.hot_industry_keywords:
            if kw in industry:
                return True
        return False

    def _has_divergence(self, s: StockScore) -> bool:
        """判断是否底背离: 价格 < MA20 且 MACD 金叉"""
        if s.ma20 is None or s.macd_dif is None or s.macd_dea is None:
            return False
        if s.prev_macd_dif is None or s.prev_macd_dea is None:
            return False
        # 价格在均线下方
        if s.close >= s.ma20:
            return False
        # MACD 金叉
        if s.macd_dif > s.macd_dea and s.prev_macd_dif <= s.prev_macd_dea:
            return True
        return False
