"""
资本周期阶段评分器
基于 ROE 轨迹 + 收入增速 + 毛利率趋势自动分类 Phase 1-5

Phase 1: 低谷整合 - ROE 低位(<10%)，行业出清阶段
Phase 2: 需求扩张 - ROE 上行，收入加速，盈利改善
Phase 3: 扩张高峰 - ROE 高位(>=18%)平台期，产能高效释放
Phase 4: 供过于求 - ROE 明显下滑，竞争加剧
Phase 5: 激烈内卷 - ROE 极低(<5%)，价格战阶段
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CapitalCycleInput:
    """资本周期评分输入（使用年报数据序列，oldest first）"""
    roe_series: list             # Annual ROE values (%), e.g. [10.5, 12.3, 15.5, 24.8]
    revenue_growth_series: list  # Annual revenue YoY growth (ratio), e.g. [0.10, 0.15, 0.45]
    gross_margin_series: list    # Annual gross margin (%), e.g. [28.0, 30.5, 33.1, 35.9]
    stock_code: str = ""
    stock_name: str = ""


@dataclass
class CapitalCycleResult:
    """资本周期评分结果"""
    phase: int          # 1-5, 0 = insufficient data
    phase_label: str    # 阶段中文标签
    score: int          # 0-100
    roe_trend: str      # "上行" / "高位平台" / "下行" / "低位平稳" / "不足"
    detail: str         # 评分依据描述
    label: str          # "偏多" / "中性偏多" / "中性" / "偏空"


class CapitalCycleScorer:
    """
    资本周期五阶段规则分类器

    Score mapping:
        Phase 1 (低谷整合): 35
        Phase 2 (需求扩张): 65
        Phase 3 (扩张高峰): 72
        Phase 4 (供过于求): 25
        Phase 5 (激烈内卷): 15
    """

    PHASE_SCORES = {1: 35, 2: 65, 3: 72, 4: 25, 5: 15}
    PHASE_LABELS = {
        0: "数据不足",
        1: "低谷整合",
        2: "需求扩张",
        3: "扩张高峰",
        4: "供过于求",
        5: "激烈内卷",
    }

    def score(self, inp: CapitalCycleInput) -> CapitalCycleResult:
        roe_series = [float(x) for x in inp.roe_series if x is not None]
        rev_series = [float(x) for x in inp.revenue_growth_series if x is not None]
        margin_series = [float(x) for x in inp.gross_margin_series if x is not None]

        if len(roe_series) < 2:
            return CapitalCycleResult(
                phase=0,
                phase_label="数据不足",
                score=50,
                roe_trend="不足",
                detail="历史ROE年报数据不足2年，默认中性",
                label="中性",
            )

        roe_current = roe_series[-1]
        roe_prev = roe_series[-2]
        roe_delta = roe_current - roe_prev

        # 3-year accumulated trend
        lookback = min(3, len(roe_series) - 1)
        roe_3yr_delta = roe_current - roe_series[-1 - lookback]

        rev_current = rev_series[-1] if rev_series else 0.0

        if len(margin_series) >= 2:
            margin_delta = margin_series[-1] - margin_series[-2]
        else:
            margin_delta = 0.0

        phase = self._classify(roe_current, roe_delta, roe_3yr_delta, rev_current, margin_delta)

        # ROE trend label
        if roe_delta > 2:
            roe_trend = "上行"
        elif roe_delta < -2:
            roe_trend = "下行"
        elif roe_current >= 15:
            roe_trend = "高位平台"
        else:
            roe_trend = "低位平稳"

        detail = (
            f"当前ROE={roe_current:.1f}%，较上年{roe_delta:+.1f}pct；"
            f"收入增速={rev_current * 100:.1f}%；"
            f"毛利率变化{margin_delta:+.1f}pct"
        )

        base_score = self.PHASE_SCORES.get(phase, 50)

        # Fine-tune within phase
        adj = 0
        if phase == 3:
            if margin_delta > 1:
                adj += 3  # margin still expanding
            if roe_current > 25:
                adj += 3  # very high ROE
            if roe_delta < -5:
                adj -= 8  # topping out fast
        elif phase == 2:
            if rev_current > 0.3:
                adj += 5  # strong revenue acceleration
            if margin_delta > 2:
                adj += 3

        final_score = max(10, min(90, base_score + adj))

        if final_score >= 68:
            label = "偏多"
        elif final_score >= 55:
            label = "中性偏多"
        elif final_score >= 35:
            label = "中性"
        else:
            label = "偏空"

        return CapitalCycleResult(
            phase=phase,
            phase_label=self.PHASE_LABELS.get(phase, "未知"),
            score=final_score,
            roe_trend=roe_trend,
            detail=detail,
            label=label,
        )

    def _classify(
        self,
        roe_cur: float,
        roe_delta: float,
        roe_3yr_delta: float,
        rev_cur: float,
        margin_delta: float,
    ) -> int:
        # Phase 5: very low ROE, still declining
        if roe_cur < 5 and roe_delta <= 0:
            return 5
        # Phase 4: clearly declining ROE
        if roe_delta <= -5 and roe_cur < 18:
            return 4
        if roe_delta <= -3 and roe_cur < 12:
            return 4
        # Phase 3: high ROE at peak/plateau
        if roe_cur >= 18 and roe_delta > -5:
            return 3
        # Phase 2: rising ROE (momentum)
        if roe_delta >= 3 and roe_cur >= 8:
            return 2
        if roe_3yr_delta >= 5 and roe_cur >= 10:
            return 2
        # Phase 1: low ROE bottom
        if roe_cur < 10:
            return 1
        # Transition zone: mild ROE improvement
        if roe_cur >= 15:
            return 3
        return 2
