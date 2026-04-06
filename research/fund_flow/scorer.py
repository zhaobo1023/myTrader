"""
资金面评分器
基于数据库 trade_stock_moneyflow 表的主力净流量数据进行评分

评分维度：
1. 5日净流入（市值归一化）
2. 20日净流入（市值归一化）
3. RPS120 相对强弱加成
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class FundFlowInput:
    """资金面评分输入"""
    net_5d_amount: float    # 近5日主力净流入合计（元）
    net_10d_amount: float   # 近10日主力净流入合计（元）
    net_20d_amount: float   # 近20日主力净流入合计（元）
    total_mv: float         # 总市值（元），用于归一化
    rps_120: float = 50.0   # 120日RPS分位 0-100，默认50（中性）


@dataclass
class FundFlowResult:
    """资金面评分结果"""
    score: int
    net_5d_pct: float       # 5日净流入 / 总市值 (%)
    net_20d_pct: float      # 20日净流入 / 总市值 (%)
    net_5d_yi: float        # 5日净流入（亿元）
    net_20d_yi: float       # 20日净流入（亿元）
    label: str
    detail: str


class FundFlowScorer:
    """
    资金面评分器（满分100，基础分50）

    5日净流入/市值:
        > +0.5%: +15  |  > +0.2%: +8  |  < -0.5%: -15  |  < -0.2%: -8

    20日净流入/市值:
        > +1.0%: +10  |  > +0.5%: +5  |  < -1.0%: -10  |  < -0.5%: -5

    RPS120 加成:
        > 80: +10  |  > 60: +5  |  < 30: -5

    最终分数 clamp 到 [10, 90]
    """

    def score(self, inp: FundFlowInput) -> FundFlowResult:
        if inp.total_mv <= 0:
            return FundFlowResult(
                score=50,
                net_5d_pct=0.0,
                net_20d_pct=0.0,
                net_5d_yi=0.0,
                net_20d_yi=0.0,
                label="中性",
                detail="市值数据缺失，默认中性",
            )

        pct_5d = inp.net_5d_amount / inp.total_mv * 100
        pct_20d = inp.net_20d_amount / inp.total_mv * 100

        s = 50

        # 5-day signal
        if pct_5d > 0.5:
            s += 15
        elif pct_5d > 0.2:
            s += 8
        elif pct_5d < -0.5:
            s -= 15
        elif pct_5d < -0.2:
            s -= 8

        # 20-day signal
        if pct_20d > 1.0:
            s += 10
        elif pct_20d > 0.5:
            s += 5
        elif pct_20d < -1.0:
            s -= 10
        elif pct_20d < -0.5:
            s -= 5

        # RPS bonus
        if inp.rps_120 > 80:
            s += 10
        elif inp.rps_120 > 60:
            s += 5
        elif inp.rps_120 < 30:
            s -= 5

        s = max(10, min(90, s))

        if s >= 70:
            label = "主力净流入"
        elif s >= 55:
            label = "中性偏多"
        elif s >= 45:
            label = "中性"
        elif s >= 30:
            label = "中性偏空"
        else:
            label = "主力净流出"

        net_5d_yi = inp.net_5d_amount / 1e8
        net_20d_yi = inp.net_20d_amount / 1e8

        detail = (
            f"5日净流入={net_5d_yi:+.2f}亿({pct_5d:+.2f}%市值)；"
            f"20日净流入={net_20d_yi:+.2f}亿({pct_20d:+.2f}%市值)；"
            f"RPS120={inp.rps_120:.1f}"
        )

        return FundFlowResult(
            score=s,
            net_5d_pct=pct_5d,
            net_20d_pct=pct_20d,
            net_5d_yi=net_5d_yi,
            net_20d_yi=net_20d_yi,
            label=label,
            detail=detail,
        )
