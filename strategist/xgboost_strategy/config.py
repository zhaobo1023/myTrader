# -*- coding: utf-8 -*-
"""
XGBoost 策略配置
"""
from dataclasses import dataclass
from typing import List


@dataclass
class StrategyConfig:
    """策略配置"""
    
    # 数据配置
    start_date: str = '2023-01-01'
    end_date: str = '2025-12-31'
    min_bars: int = 120  # 最少需要的K线数量
    
    # 训练配置
    train_window: int = 120  # 训练窗口（交易日）
    predict_horizon: int = 5  # 预测未来N日收益率
    roll_step: int = 5  # 滚动步长
    
    # XGBoost 超参数
    n_estimators: int = 50
    max_depth: int = 4
    learning_rate: float = 0.05
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    random_state: int = 42
    
    # 预处理配置
    preprocess_method: str = 'mad'  # 'mad' 或 'robust_zscore'
    mad_multiplier: float = 5.0  # MAD 去极值倍数
    clip_range: float = 3.0  # RobustZScore 裁剪范围
    
    # 股票池配置
    stock_pool: List[str] = None  # None 表示使用所有股票
    min_stocks_per_day: int = 10  # 每日最少股票数
    
    # 回测配置
    top_n: int = 10  # 买入预测排名前N的股票
    rebalance_freq: int = 5  # 调仓频率（天）
    
    def __post_init__(self):
        """初始化后处理"""
        if self.stock_pool is None:
            # 默认使用50只代表性A股大盘股
            self.stock_pool = [
                '600519.SH', '000858.SZ', '601318.SH', '600036.SH', '000333.SZ',
                '600900.SH', '601166.SH', '000001.SZ', '600276.SH', '601888.SH',
                '002594.SZ', '300750.SZ', '601398.SH', '601939.SH', '600030.SH',
                '000651.SZ', '002415.SZ', '600309.SH', '600887.SH', '601012.SH',
                '000568.SZ', '002304.SZ', '600050.SH', '601668.SH', '600000.SH',
                '000002.SZ', '601857.SH', '600585.SH', '002352.SZ', '600104.SH',
                '601601.SH', '600690.SH', '601288.SH', '600028.SH', '601138.SH',
                '002714.SZ', '300059.SZ', '002475.SZ', '600031.SH', '300760.SZ',
                '601899.SH', '600809.SH', '000725.SZ', '002230.SZ', '601919.SH',
                '300015.SZ', '002142.SZ', '600438.SH', '601225.SH', '002027.SZ',
            ]
    
    def get_xgboost_params(self) -> dict:
        """获取 XGBoost 参数字典"""
        return {
            'n_estimators': self.n_estimators,
            'max_depth': self.max_depth,
            'learning_rate': self.learning_rate,
            'subsample': self.subsample,
            'colsample_bytree': self.colsample_bytree,
            'random_state': self.random_state,
            'verbosity': 0,
        }
