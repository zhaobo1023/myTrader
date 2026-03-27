# -*- coding: utf-8 -*-
"""
信号生成模块

在指定信号日调用 XGBoost 策略，返回股票列表 + 预测分值。

关键约束:
- 只使用 signal_date 及之前的数据
- 训练集截止到 signal_date - 1
- 不使用 signal_date 之后任何价格
"""
import logging
from datetime import date

import pandas as pd

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from .config import PaperTradingConfig

logger = logging.getLogger(__name__)


class SignalGenerator:
    """信号生成器"""

    def __init__(self, pt_config: PaperTradingConfig = None):
        self.pt_config = pt_config or PaperTradingConfig()

    def generate(self, signal_date: date, index_name: str) -> pd.DataFrame:
        """
        在 signal_date 当天生成选股信号。

        Args:
            signal_date: 信号生成日
            index_name: 指数池名称（如 '沪深300'）

        Returns:
            DataFrame，列: stock_code, pred_score, pred_rank
            包含预测排名前 top_n 的股票
        """
        # 延迟导入避免循环依赖
        from strategist.xgboost_strategy.data_loader import DataLoader
        from strategist.xgboost_strategy.model_trainer import ModelTrainer
        from strategist.xgboost_strategy.config import StrategyConfig

        # 1. 构建 XGBoost 配置
        xgb_config = StrategyConfig()
        xgb_config.train_window = self.pt_config.xgb_train_window
        xgb_config.predict_horizon = self.pt_config.xgb_predict_horizon

        # 2. 加载数据（截止到 signal_date）
        signal_date_str = signal_date.strftime('%Y-%m-%d')
        logger.info(f"加载因子数据，截止日期: {signal_date_str}，指数池: {index_name}")

        # 计算起始日期：需要至少 train_window + predict_horizon + min_bars 个交易日
        # 向前推约 2 年确保有足够数据
        start_date = (signal_date - pd.Timedelta(days=730)).strftime('%Y-%m-%d')

        loader = DataLoader(xgb_config)
        panel, feature_cols = loader.load_and_compute_factors(
            start_date=start_date,
            end_date=signal_date_str,
        )

        if panel is None or len(panel) == 0:
            raise ValueError(f"无法加载因子数据，截止日期: {signal_date_str}")

        # 3. 验证数据边界（防止 look-ahead bias）
        panel['trade_date'] = pd.to_datetime(panel['trade_date'])
        max_date = panel['trade_date'].max().date()
        if max_date > signal_date:
            raise ValueError(
                f"数据泄露警告：面板数据包含 {max_date}，超过信号日 {signal_date}"
            )

        # 4. 去除 signal_date 当天没有 future_ret 的数据（正常，最后几天没有标签）
        # 但 signal_date 截面必须有特征数据用于预测
        signal_panel = panel[panel['trade_date'] == pd.Timestamp(signal_date)]
        if len(signal_panel) == 0:
            raise ValueError(f"信号日 {signal_date} 没有截面数据")

        logger.info(f"信号日截面: {len(signal_panel)} 只股票，{len(feature_cols)} 个因子")

        # 5. 使用 predict_on_date 训练并预测
        trainer = ModelTrainer(xgb_config)
        predictions = trainer.predict_on_date(
            panel=panel,
            feature_cols=feature_cols,
            pred_date=signal_date_str,
        )

        # 6. 排名，取 Top N
        predictions['pred_rank'] = predictions['pred_score'].rank(
            ascending=False, method='first'
        ).astype(int)

        top_n = predictions.nsmallest(self.pt_config.top_n, 'pred_rank')
        result = top_n[['stock_code', 'pred_score', 'pred_rank']].reset_index(drop=True)

        logger.info(
            f"信号生成完成: 选出 {len(result)} 只股票 "
            f"(Top {self.pt_config.top_n})"
        )
        logger.info(f"前5只: {result.head()['stock_code'].tolist()}")

        return result
