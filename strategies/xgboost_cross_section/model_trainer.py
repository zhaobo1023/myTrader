# -*- coding: utf-8 -*-
"""
XGBoost 模型训练器

实现滚动窗口训练策略
"""
import numpy as np
import pandas as pd
from typing import List, Tuple, Optional
import logging

try:
    from xgboost import XGBRegressor
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False

from .config import StrategyConfig

logger = logging.getLogger(__name__)


class ModelTrainer:
    """XGBoost 滚动窗口训练器"""

    def __init__(self, config: StrategyConfig = None):
        """
        初始化训练器

        参数:
            config: 策略配置
        """
        if not HAS_XGBOOST:
            raise ImportError("XGBoost 未安装，请运行: pip install xgboost")

        self.config = config or StrategyConfig()
        self.model = None

    def create_model(self):
        """创建 XGBoost 模型"""
        return XGBRegressor(**self.config.get_xgboost_params())

    def train(self, X_train, y_train):
        """
        训练模型

        参数:
            X_train: 训练特征
            y_train: 训练标签

        返回:
            训练好的模型
        """
        self.model = self.create_model()
        self.model.fit(X_train, y_train)
        return self.model

    def predict(self, X_test):
        """
        预测

        参数:
            X_test: 测试特征

        返回:
            预测值
        """
        if self.model is None:
            raise ValueError("模型未训练，请先调用 train()")

        return self.model.predict(X_test)

    def rolling_train_predict(
        self,
        panel: pd.DataFrame,
        feature_cols: List[str],
        dates: List,
    ) -> List[dict]:
        """
        滚动窗口训练和预测

        训练数据: [pred_idx - train_window, pred_idx - 1]，严格不含 pred_date
        预测数据: pred_date 当天的截面

        参数:
            panel: 面板数据，包含 trade_date, stock_code, feature_cols, future_ret
            feature_cols: 特征列名列表
            dates: 所有交易日列表

        返回:
            预测结果列表，每个元素为 {pred_date, predictions, stock_codes}
        """
        results = []

        train_window = self.config.train_window
        roll_step = self.config.roll_step

        predict_indices = list(range(train_window, len(dates), roll_step))
        total_predictions = len(predict_indices)

        logger.info(f"开始滚动训练预测: {total_predictions} 次")

        for step, pred_idx in enumerate(predict_indices):
            pred_date = dates[pred_idx]

            # 训练数据: [pred_idx - train_window, pred_idx - 1]，严格不含 pred_date
            train_dates = dates[pred_idx - train_window : pred_idx]
            train_data = panel[panel['trade_date'].isin(train_dates)].copy()

            # 去掉训练集中 future_ret 为 NaN 的行（最后几天没有标签）
            train_data = train_data.dropna(subset=['future_ret'])

            # 预测数据: 只用 pred_date 当天的截面
            test_data = panel[panel['trade_date'] == pred_date].copy()

            if len(test_data) < self.config.min_stocks_per_day or len(train_data) < 100:
                logger.warning(f"日期 {pred_date}: 数据不足，跳过")
                continue

            # 准备特征和标签
            X_train = train_data[feature_cols].fillna(0).values
            y_train = train_data['future_ret'].values
            X_test = test_data[feature_cols].fillna(0).values

            # 训练和预测
            self.train(X_train, y_train)
            y_pred = self.predict(X_test)

            # 保存结果（不记录 actual，actual 在 backtest 里按 T+1 买入价计算）
            results.append({
                'pred_date': pred_date,
                'predictions': y_pred,
                'stock_codes': test_data['stock_code'].values,
            })

            if (step + 1) % 20 == 0:
                logger.info(f"进度: {step+1}/{total_predictions}")

        logger.info(f"滚动训练预测完成: {len(results)} 次有效预测")
        return results

    def predict_on_date(
        self,
        panel: pd.DataFrame,
        feature_cols: List[str],
        pred_date: str,
    ) -> pd.DataFrame:
        """
        对指定日期进行单次截面预测。

        仅使用 pred_date 之前的数据训练，对 pred_date 截面进行预测。

        参数:
            panel: 面板数据，包含 trade_date, stock_code, feature_cols, future_ret
            feature_cols: 特征列名列表
            pred_date: 预测日期，格式 'YYYY-MM-DD'

        返回:
            DataFrame，列: stock_code, pred_score
        """
        pred_date_ts = pd.Timestamp(pred_date)

        # 获取所有交易日
        dates = sorted(panel['trade_date'].unique())

        # 找到 pred_date 在 dates 中的位置
        if pred_date_ts not in dates:
            raise ValueError(f"日期 {pred_date} 不在面板数据的交易日中")

        pred_idx = dates.index(pred_date_ts)
        train_window = self.config.train_window

        # 训练数据: [pred_idx - train_window, pred_idx - 1]
        if pred_idx < train_window:
            raise ValueError(
                f"训练数据不足: 需要至少 {train_window} 个交易日，"
                f"但 {pred_date} 前只有 {pred_idx} 个交易日"
            )

        train_dates = dates[pred_idx - train_window : pred_idx]
        train_data = panel[panel['trade_date'].isin(train_dates)].copy()
        train_data = train_data.dropna(subset=['future_ret'])

        # 预测数据: pred_date 截面
        test_data = panel[panel['trade_date'] == pred_date_ts].copy()

        if len(test_data) < self.config.min_stocks_per_day:
            raise ValueError(f"日期 {pred_date} 截面股票数不足: {len(test_data)}")

        if len(train_data) < 100:
            raise ValueError(f"日期 {pred_date} 训练数据不足: {len(train_data)}")

        X_train = train_data[feature_cols].fillna(0).values
        y_train = train_data['future_ret'].values
        X_test = test_data[feature_cols].fillna(0).values

        self.train(X_train, y_train)
        y_pred = self.predict(X_test)

        result = pd.DataFrame({
            'stock_code': test_data['stock_code'].values,
            'pred_score': y_pred,
        })

        logger.info(f"单日预测完成: {pred_date}, {len(result)} 只股票")
        return result

    def get_feature_importance(self, feature_cols: List[str]) -> pd.DataFrame:
        """
        获取特征重要性

        参数:
            feature_cols: 特征列名列表

        返回:
            DataFrame with feature and importance
        """
        if self.model is None:
            raise ValueError("模型未训练")

        importance = self.model.feature_importances_

        df = pd.DataFrame({
            'feature': feature_cols,
            'importance': importance,
        })
        df = df.sort_values('importance', ascending=False)

        return df
