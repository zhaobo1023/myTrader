# -*- coding: utf-8 -*-
"""
技术面扫描配置
"""
from pathlib import Path
from dataclasses import dataclass, field
from typing import List


@dataclass
class ScanConfig:
    """扫描配置"""
    
    # 文件路径
    portfolio_file: str = "/Users/zhaobo/Documents/notes/Finance/Positions/00-Current-Portfolio-Audit.md"
    output_dir: str = "/Users/zhaobo/Documents/notes/Finance/TechScanEveryDay"
    log_dir: str = "output/tech_scan"
    
    # 数据库环境
    db_env: str = "online"
    
    # 均线参数
    ma_windows: List[int] = field(default_factory=lambda: [5, 20, 60, 250])
    
    # RSI 参数
    rsi_period: int = 14
    
    # MACD 参数
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    
    # 信号阈值
    pullback_threshold: float = 0.015  # 回踩阈值 ±1.5%
    volume_ratio_threshold: float = 1.5  # 放量阈值
    rsi_overbought: int = 70
    rsi_oversold: int = 30
    rps_warning_threshold: int = 80  # RPS 预警线
    
    # 数据查询范围（交易日）
    lookback_days: int = 300  # 确保 MA250 可计算
    
    # 定时任务
    schedule_time: str = "16:30"
    
    def ensure_dirs(self):
        """确保输出目录存在"""
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        Path(self.log_dir).mkdir(parents=True, exist_ok=True)


# 默认配置实例
DEFAULT_CONFIG = ScanConfig()
