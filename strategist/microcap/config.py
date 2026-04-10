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
    min_avg_turnover: float = 0.0        # 近 5 日平均成交额最低要求（元），0 表示不过滤
                                         # 建议实盘前设为 5_000_000（500 万）

    # 输出配置
    output_dir: Optional[str] = None     # 输出目录，None 则使用默认 output/microcap

    def __post_init__(self):
        """初始化后处理"""
        if self.output_dir is None:
            import os
            root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.output_dir = os.path.join(root, 'output', 'microcap')
