# -*- coding: utf-8 -*-
"""
截面预测器

基于训练好的模型进行截面预测
"""
import numpy as np
import pandas as pd
from typing import List, Dict
import logging

from .model_trainer import ModelTrainer
from .config import StrategyConfig

logger = logging.getLogger(__name__)


class Predictor:
    """截面预测器"""
    
    def __init__(self, config: StrategyConfig = None):
        """
        初始化预测器
        
        参数:
            config: 策略配置
        """
        self.config = config or StrategyConfig()
        self.trainer = ModelTrainer(config)
    
    def predict_cross_section(
        self,
        panel: pd.DataFrame,
        feature_cols: List[str],
    ) -> List[Dict]:
        """
        截面预测：滚动训练并预测每日的股票收益率排名
        
        参数:
            panel: 面板数据，包含 trade_date, stock_code, feature_cols, future_ret
            feature_cols: 特征列名列表
        
        返回:
            预测结果列表
        """
        # 获取所有交易日
        dates = sorted(panel['trade_date'].unique())
        
        logger.info(f"交易日数: {len(dates)}")
        logger.info(f"日期范围: {dates[0]} ~ {dates[-1]}")
        
        # 滚动训练预测
        results = self.trainer.rolling_train_predict(panel, feature_cols, dates)
        
        return results
    
    def get_top_stocks(
        self,
        predictions: np.ndarray,
        stock_codes: np.ndarray,
        top_n: int = None,
    ) -> List[str]:
        """
        获取预测排名前 N 的股票
        
        参数:
            predictions: 预测值数组
            stock_codes: 股票代码数组
            top_n: 选择前 N 只股票
        
        返回:
            股票代码列表
        """
        if top_n is None:
            top_n = self.config.top_n
        
        # 按预测值降序排序
        sorted_indices = np.argsort(predictions)[::-1]
        top_indices = sorted_indices[:top_n]
        
        return stock_codes[top_indices].tolist()
    
    def generate_signals(self, results: List[Dict]) -> pd.DataFrame:
        """
        生成交易信号
        
        参数:
            results: 预测结果列表
        
        返回:
            DataFrame with date, stock_code, prediction, actual, rank
        """
        all_signals = []
        
        for result in results:
            date = result['date']
            predictions = result['predictions']
            actuals = result['actuals']
            stock_codes = result['stock_codes']
            
            # 计算排名
            pred_ranks = pd.Series(predictions).rank(ascending=False, method='min')
            
            for i, code in enumerate(stock_codes):
                all_signals.append({
                    'date': date,
                    'stock_code': code,
                    'prediction': predictions[i],
                    'actual': actuals[i] if not np.isnan(actuals[i]) else None,
                    'pred_rank': int(pred_ranks.iloc[i]),
                })
        
        df = pd.DataFrame(all_signals)
        return df
    
    def get_daily_top_stocks(self, signals: pd.DataFrame, top_n: int = None) -> Dict:
        """
        获取每日的 Top N 股票
        
        参数:
            signals: 信号 DataFrame
            top_n: 选择前 N 只股票
        
        返回:
            {date: [stock_codes]}
        """
        if top_n is None:
            top_n = self.config.top_n
        
        daily_tops = {}
        
        for date, group in signals.groupby('date'):
            top_stocks = group.nsmallest(top_n, 'pred_rank')['stock_code'].tolist()
            daily_tops[date] = top_stocks
        
        return daily_tops
