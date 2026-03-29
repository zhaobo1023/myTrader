# -*- coding: utf-8 -*-
"""
SVD 市场监控配置
"""
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class SVDMonitorConfig:
    """SVD 市场监控参数配置"""

    # 多尺度窗口配置: {window_size: step}
    windows: Dict[int, int] = field(default_factory=lambda: {
        20: 5,    # 短窗口: 高灵敏, 5日步长
        60: 10,   # 中窗口: 中等灵敏, 10日步长
        120: 20,  # 长窗口: 低滞后, 20日步长
    })

    # Randomized SVD 成分数
    n_components: int = 10

    # 停牌/僵尸股过滤: 窗口期内至少 80% 交易日有效
    min_valid_days_ratio: float = 0.80

    # 最小有效股票数 (低于此数跳过窗口)
    min_stock_count: int = 50

    # 突变检测参数
    mutation_sigma_trigger: float = 2.0     # 触发阈值: 偏离 2σ
    mutation_sigma_release: float = 1.5     # 解除阈值: 回归 1.5σ
    mutation_cooldown_days: int = 3         # 冷却期: 至少持续 3 个交易日

    # 多尺度加权投票权重
    base_weights: Dict[int, float] = field(default_factory=lambda: {
        120: 0.50,
        60: 0.30,
        20: 0.20,
    })

    # 突变触发时权重重分配
    mutation_weights: Dict[int, float] = field(default_factory=lambda: {
        20: 0.50,
        60: 0.20,
        120: 0.30,
    })

    # 市场状态阈值
    state_threshold_high: float = 0.50      # > 50% = 齐涨齐跌
    state_threshold_low: float = 0.35       # < 35% = 个股行情

    # 行业中性化开关 (默认关闭: 监控全市场 Beta 压力)
    industry_neutral: bool = False

    # MAD 去极值参数
    mad_n: float = 3.0  # ±3 中位差截断

    # 输出目录
    output_dir: str = 'output/svd_monitor'
