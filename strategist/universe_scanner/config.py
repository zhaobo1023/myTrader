# -*- coding: utf-8 -*-
"""
全量自选股扫描配置
"""
from pathlib import Path
from dataclasses import dataclass, field
from typing import List


@dataclass
class UniverseScanConfig:
    """全量扫描配置"""

    # ---- 文件路径 ----
    universe_csv: str = "/Users/zhaobo/Documents/notes/Finance/总池子.csv"
    output_dir: str = "/Users/zhaobo/Documents/notes/Finance"
    log_dir: str = "output/universe_scan"

    # ---- 数据库 ----
    db_env: str = "online"
    lookback_days: int = 300  # 自然日，确保 MA250 可计算

    # ---- 海选池过滤 (Step 1) ----
    # 剔除流动性差的标的
    min_avg_amount: float = 5000.0  # 60 日均成交额 >= 5000 万
    # 剔除长期下降通道（MA250 线下且无放量）
    ma250_required: bool = True  # 价格必须在 MA250 上方

    # ---- 动态关注池门槛 (Step 2) ----
    rps_min: int = 80           # RPS(120) 或 RPS(250) 必须 > 80
    trend_ma_options: List[int] = field(default_factory=lambda: [20, 60])  # 价格在 MA20 或 MA60 之上

    # ---- 核心监控池门槛 (Step 3) ----
    high_priority_top_n: int = 30  # 按总分取前 30 只

    # ---- 评分权重 ----
    # +2: MACD 金叉 或 均线多头排列
    score_macd_golden_cross: int = 2
    score_ma_bullish: int = 2
    # +2: 热门行业
    score_hot_industry: int = 2
    # +3: 底背离 或 RPS 创新高
    score_divergence: int = 3
    score_rps_new_high: int = 3
    # +1: 放量突破
    score_volume_breakout: int = 1
    # +1: RSI 超卖反弹区间 (30-50)
    score_rsi_oversold_bounce: int = 1
    # -2: RSI 超买 (> 80) 追高风险
    score_rsi_overbought: int = -2
    # -1: 缩量回调
    score_shrink_pullback: int = -1

    # ---- 热门行业关键词 ----
    hot_industry_keywords: List[str] = field(default_factory=lambda: [
        "核", "核电", "核力", "新材料", "电力", "电力设备", "半导体",
        "人工智能", "机器人", "军工", "国防", "新能源", "储能",
        "锂电", "光伏", "氢能", "铜", "小金属", "稀土", "贵金属",
        "黄金", "消费电子", "通信设备", "软件开发", "计算机",
        "医疗器械", "创新药", "生物制品",
    ])

    # ---- 信号阈值 (复用 tech_scan) ----
    volume_ratio_threshold: float = 1.5
    rsi_overbought: int = 80
    rsi_oversold: int = 30
    rps_new_high_threshold: int = 95  # RPS >= 95 视为创新高

    # ---- 定时任务 ----
    schedule_time: str = "18:00"

    def ensure_dirs(self):
        """确保输出目录存在"""
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        Path(self.log_dir).mkdir(parents=True, exist_ok=True)


DEFAULT_CONFIG = UniverseScanConfig()
