# -*- coding: utf-8 -*-
"""
Paper Trading 配置模块

定义模拟交易的各项参数：持仓天数、选股数量、交易成本、指数池等。
"""
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class PaperTradingConfig:
    """Paper Trading 配置"""

    # ========== 持仓参数 ==========
    hold_days: int = 5                # 持仓交易日数（T+1 买入，T+1+hold_days 卖出）
    top_n: int = 10                   # 每轮选股数量
    cost_rate: float = 0.002          # 双边交易成本（0.2%）

    # ========== 指数池 ==========
    index_pool: Dict[str, str] = field(default_factory=lambda: {
        '上证50':   '000016.SH',
        '沪深300':  '000300.SH',
        '中证500':  '000905.SH',
        '中证1000': '000852.SH',
        '中证2000': '932000.CSI',
    })

    # ========== 默认参数 ==========
    default_index: str = '沪深300'    # 默认指数池

    # ========== 信号生成（对接 XGBoost 策略） ==========
    xgb_train_window: int = 120       # 训练窗口（交易日）
    xgb_predict_horizon: int = 5      # 预测未来 N 日收益率

    # ========== 报告输出 ==========
    output_dir: str = field(default_factory=lambda: os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 'output'
    ))
    report_min_rounds: int = 4        # 至少几轮才生成评估报告

    # ========== 调仓周期 ==========
    rebalance_weekday: int = 4        # 每周几生成信号（4=周五）

    def get_index_code(self, index_name: str) -> Optional[str]:
        """根据指数名称获取指数代码"""
        return self.index_pool.get(index_name)

    def get_available_indexes(self) -> List[str]:
        """获取可用的指数名称列表"""
        return list(self.index_pool.keys())
