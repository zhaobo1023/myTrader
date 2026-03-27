# -*- coding: utf-8 -*-
"""
XGBoost 策略回测框架

基于预测排名进行选股回测
"""
import pandas as pd
import numpy as np
from typing import Dict, List
import logging

from .predictor import Predictor
from .evaluator import ICEvaluator
from .config import StrategyConfig

logger = logging.getLogger(__name__)


class XGBoostBacktest:
    """XGBoost 策略回测"""
    
    def __init__(self, config: StrategyConfig = None):
        """
        初始化回测
        
        参数:
            config: 策略配置
        """
        self.config = config or StrategyConfig()
        self.predictor = Predictor(config)
        self.evaluator = ICEvaluator()
    
    def run_backtest(
        self,
        panel: pd.DataFrame,
        feature_cols: List[str],
    ) -> Dict:
        """
        运行回测
        
        参数:
            panel: 面板数据
            feature_cols: 特征列名列表
        
        返回:
            回测结果字典
        """
        logger.info("=" * 60)
        logger.info("开始 XGBoost 截面预测回测")
        logger.info("=" * 60)
        
        # 1. 截面预测
        logger.info("\n[1/4] 截面预测...")
        results = self.predictor.predict_cross_section(panel, feature_cols)
        
        if not results:
            logger.error("预测失败")
            return {}
        
        # 2. IC 评估
        logger.info("\n[2/4] IC 评估...")
        metrics = self.evaluator.evaluate_predictions(results)
        self.evaluator.print_metrics(metrics)
        
        # 3. 生成交易信号
        logger.info("\n[3/4] 生成交易信号...")
        signals = self.predictor.generate_signals(results)
        daily_tops = self.predictor.get_daily_top_stocks(signals, self.config.top_n)
        
        logger.info(f"生成信号: {len(signals)} 条")
        logger.info(f"交易日数: {len(daily_tops)}")
        
        # 4. 计算组合收益
        logger.info("\n[4/4] 计算组合收益...")
        portfolio_returns = self.calc_portfolio_returns(signals, daily_tops)
        
        # 汇总结果
        result = {
            'metrics': metrics,
            'signals': signals,
            'daily_tops': daily_tops,
            'portfolio_returns': portfolio_returns,
            'results': results,
        }
        
        logger.info("\n" + "=" * 60)
        logger.info("回测完成")
        logger.info("=" * 60)
        
        return result
    
    def calc_portfolio_returns(
        self,
        signals: pd.DataFrame,
        daily_tops: Dict,
    ) -> pd.DataFrame:
        """
        计算组合收益
        
        参数:
            signals: 信号 DataFrame
            daily_tops: 每日 Top N 股票
        
        返回:
            DataFrame with date, portfolio_return, benchmark_return
        """
        portfolio_rets = []
        
        for date, top_stocks in daily_tops.items():
            # 获取当日 Top N 股票的实际收益
            day_signals = signals[
                (signals['date'] == date) & 
                (signals['stock_code'].isin(top_stocks))
            ]
            
            if len(day_signals) == 0:
                continue
            
            # 等权组合收益
            valid_rets = day_signals['actual'].dropna()
            if len(valid_rets) > 0:
                portfolio_ret = valid_rets.mean()
            else:
                portfolio_ret = 0
            
            # 全市场平均收益作为基准
            all_day_signals = signals[signals['date'] == date]
            benchmark_ret = all_day_signals['actual'].mean()
            
            portfolio_rets.append({
                'date': date,
                'portfolio_return': portfolio_ret,
                'benchmark_return': benchmark_ret,
                'excess_return': portfolio_ret - benchmark_ret,
                'n_stocks': len(valid_rets),
            })
        
        df = pd.DataFrame(portfolio_rets)
        
        if len(df) > 0:
            # 计算累计收益
            df['cum_portfolio'] = (1 + df['portfolio_return']).cumprod()
            df['cum_benchmark'] = (1 + df['benchmark_return']).cumprod()
            df['cum_excess'] = (1 + df['excess_return']).cumprod()
            
            # 打印统计
            total_ret = df['cum_portfolio'].iloc[-1] - 1
            benchmark_ret = df['cum_benchmark'].iloc[-1] - 1
            excess_ret = total_ret - benchmark_ret
            
            logger.info(f"组合总收益: {total_ret*100:+.2f}%")
            logger.info(f"基准总收益: {benchmark_ret*100:+.2f}%")
            logger.info(f"超额收益:   {excess_ret*100:+.2f}%")
            logger.info(f"平均持仓:   {df['n_stocks'].mean():.1f} 只")
        
        return df
    
    def analyze_factor_ic(self, panel: pd.DataFrame, feature_cols: List[str]) -> pd.DataFrame:
        """
        单因子 IC 分析
        
        参数:
            panel: 面板数据
            feature_cols: 特征列名列表
        
        返回:
            因子 IC 统计 DataFrame
        """
        return self.evaluator.analyze_factor_ic(panel, feature_cols)
