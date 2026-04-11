# -*- coding: utf-8 -*-
"""
Microcap PEG 策略配置
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class MicrocapConfig:
    """微市值 PEG 策略配置"""

    # 数据范围
    start_date: str = '2022-01-01'
    end_date: str = '2026-03-31'

    # 股票池配置
    market_cap_percentile: float = 0.20  # 市值后 20% 的股票
    exclude_st: bool = True              # 排除 ST/*ST
    min_pe_ttm: float = 0.0              # PE_TTM 最小值（排除无效数据）

    # 因子配置
    factor: str = 'peg'                  # 因子名: peg / ebit_ratio

    # 回测参数
    top_n: int = 15                      # 选股数量
    hold_days: int = 1                   # 持有天数
    # 成本率说明：
    #   buy_cost_rate:  买入单边费率（默认 0.03% 佣金，无印花税）
    #   sell_cost_rate: 卖出单边费率（默认 0.03% 佣金 + 0.1% 印花税 = 0.13%）
    #   历史测试用 cost_rate=0.002 是双边各扣一次，过于保守；改为非对称更真实
    buy_cost_rate: float = 0.0003        # 买入费率（0.03%）
    sell_cost_rate: float = 0.0013       # 卖出费率（0.13% = 佣金0.03% + 印花税0.1%）
    slippage_rate: float = 0.001         # 单边滑点（0.1%，微盘股买卖价差+冲击成本）

    # 基准对比
    benchmark_code: str = '399303'       # 基准指数代码（399303=国证2000，空字符串跳过）

    # 流动性过滤
    min_avg_turnover: float = 5_000_000.0  # 近 5 日平均成交额最低要求（元），500万下限

    # 财务风险过滤（排除雷区股）
    exclude_risk: bool = False           # 是否启用财务风险过滤
    max_debt_ratio: float = 0.70         # 资产负债率上限（排除 > 70%）
    require_positive_profit: bool = True # 要求最近年报净利润 > 0（排除亏损股）
    require_positive_cashflow: bool = True  # 要求最近年报经营现金流 > 0

    # 月度日历择时
    calendar_timing: bool = False            # 是否启用
    weak_months: tuple = (1, 4, 12)          # 弱月份
    weak_month_ratio: float = 0.5            # 弱月持仓比例 (top_n * ratio)

    # 动量反转因子 (factor='pure_mv_mom' 时生效)
    momentum_lookback: int = 20              # 回看天数
    momentum_weight: float = 0.3             # 反转权重 (0~1)

    # 动态市值止盈
    dynamic_cap_exit: bool = False           # 是否启用
    cap_exit_percentile: float = 0.50        # 全市场市值百分位阈值（超过即卖出）

    # 输出配置
    output_dir: Optional[str] = None     # 输出目录，None 则使用默认 output/microcap

    def __post_init__(self):
        """初始化后处理"""
        if self.output_dir is None:
            import os
            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.output_dir = os.path.join(root, 'output', 'microcap')
