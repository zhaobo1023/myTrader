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
        benchmark_ret_series: pd.Series = None,
    ) -> Dict:
        """
        运行回测

        参数:
            panel: 面板数据（含 trade_date, stock_code, open, close, feature_cols, future_ret）
            feature_cols: 特征列名列表
            benchmark_ret_series: 基准指数日收益率序列，index=trade_date, values=日收益率(小数)
                                 若为 None，则使用全市场等权作为基准

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
        metrics = self.evaluator.evaluate_predictions(results, panel)
        self.evaluator.print_metrics(metrics)

        # 3. 生成交易信号
        logger.info("\n[3/4] 生成交易信号...")
        signals = self.predictor.generate_signals(results)
        daily_tops = self.predictor.get_daily_top_stocks(signals, self.config.top_n)

        logger.info(f"生成信号: {len(signals)} 条")
        logger.info(f"交易日数: {len(daily_tops)}")

        # 4. 计算组合收益（传入 panel 用于查询价格）
        logger.info("\n[4/4] 计算组合收益...")
        bm_label = "指数基准" if benchmark_ret_series is not None else "全市场等权"
        logger.info(f"基准类型: {bm_label}")
        portfolio_returns = self.calc_portfolio_returns(results, panel, benchmark_ret_series)

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
        results: List[Dict],
        panel: pd.DataFrame,
        benchmark_ret_series: pd.Series = None,
    ) -> pd.DataFrame:
        """
        计算组合收益 — T+1 买入，T+1+hold_period 卖出

        时间轴:
          T日（信号生成日）  → T+1日（买入） → T+1+hold_period日（卖出）

        参数:
            results: rolling_train_predict 的输出
            panel: 含 trade_date, stock_code, open, close 的完整数据
            benchmark_ret_series: 基准指数日收益率，index=trade_date(Timestamp), values=日收益率(小数)
                                 若为 None，回退到全市场等权基准

        返回:
            DataFrame with signal_date, buy_date, sell_date, portfolio_ret, benchmark_ret, ...
        """
        # 建立价格查询表（去重防止重复索引）
        price_df = panel[['stock_code', 'trade_date', 'close']].drop_duplicates(
            subset=['stock_code', 'trade_date']
        )
        price_table = price_df.set_index(['stock_code', 'trade_date'])['close']
        all_dates = sorted(panel['trade_date'].unique())
        date_to_idx = {d: i for i, d in enumerate(all_dates)}

        # 构建基准日收益率查找表
        if benchmark_ret_series is not None:
            bm_daily = benchmark_ret_series.to_dict()
            logger.info(f"使用指数基准: {len(bm_daily)} 个交易日")

        hold_period = self.config.predict_horizon  # 默认5天
        top_n = self.config.top_n
        cost = 0.002  # 双边交易成本 0.2%

        portfolio_records = []

        for signal in results:
            pred_date = signal['pred_date']  # T日：信号生成日
            stocks = signal['stock_codes']
            preds = signal['predictions']

            # 按预测值排名，取 Top N
            ranked = sorted(zip(stocks, preds), key=lambda x: -x[1])
            top_stocks = [s for s, _ in ranked[:top_n]]

            # 买入日：T+1 日（下一个交易日）
            t_idx = date_to_idx.get(pred_date)
            if t_idx is None or t_idx + 1 >= len(all_dates):
                continue
            buy_date = all_dates[t_idx + 1]

            # 卖出日：T+1+hold_period 日
            sell_idx = t_idx + 1 + hold_period
            if sell_idx >= len(all_dates):
                continue
            sell_date = all_dates[sell_idx]

            # 计算每只 Top N 股票的实际收益
            stock_rets = []
            for stk in top_stocks:
                try:
                    bp = float(price_table.loc[(stk, buy_date)])
                    sp = float(price_table.loc[(stk, sell_date)])
                    if bp <= 0 or np.isnan(bp) or np.isnan(sp):
                        continue
                    stock_rets.append(float(sp / bp - 1))
                except (KeyError, TypeError, ValueError):
                    continue  # 停牌或数据缺失

            if not stock_rets:
                continue

            portfolio_ret = float(np.mean(stock_rets))

            # 基准收益
            if benchmark_ret_series is not None:
                # 指数基准：买入日到卖出日之间的累计指数收益
                # 买入日收盘买入，卖出日收盘卖出 → 指数 hold_period 日涨幅
                # 涨跌幅 = (sell_close / buy_close) - 1
                bm_ret = 0.0
                if buy_date in bm_daily and sell_date in bm_daily:
                    # bm_daily 存的是每日涨跌幅(小数)，需要累计
                    cum_bm = 1.0
                    d_idx = date_to_idx.get(buy_date)
                    for k in range(hold_period):
                        if d_idx + k + 1 < len(all_dates):
                            d = all_dates[d_idx + k + 1]
                            if d in bm_daily:
                                cum_bm *= (1 + bm_daily[d])
                    bm_ret = cum_bm - 1.0
                benchmark_ret = float(bm_ret)
            else:
                # 回退：全市场等权基准
                benchmark_stocks = panel[panel['trade_date'] == buy_date]['stock_code'].tolist()
                bm_rets = []
                for stk in benchmark_stocks:
                    try:
                        bp = float(price_table.loc[(stk, buy_date)])
                        sp = float(price_table.loc[(stk, sell_date)])
                        if bp <= 0 or np.isnan(bp) or np.isnan(sp):
                            continue
                        bm_rets.append(float(sp / bp - 1))
                    except (KeyError, TypeError, ValueError):
                        continue
                benchmark_ret = float(np.mean(bm_rets)) if bm_rets else 0.0

            # 扣除交易成本
            net_portfolio_ret = portfolio_ret - cost

            portfolio_records.append({
                'signal_date': pred_date,
                'buy_date': buy_date,
                'sell_date': sell_date,
                'portfolio_ret': net_portfolio_ret,
                'benchmark_ret': benchmark_ret,
                'excess_ret': net_portfolio_ret - benchmark_ret,
                'n_stocks': len(stock_rets),
                'top_stocks': ','.join(top_stocks),
            })

        df = pd.DataFrame(portfolio_records)

        if len(df) > 0:
            # 计算累计收益
            df['cum_portfolio'] = (1 + df['portfolio_ret']).cumprod()
            df['cum_benchmark'] = (1 + df['benchmark_ret']).cumprod()
            df['cum_excess'] = (1 + df['excess_ret']).cumprod()

            # 打印统计
            total_ret = df['cum_portfolio'].iloc[-1] - 1
            benchmark_ret = df['cum_benchmark'].iloc[-1] - 1
            excess_ret = total_ret - benchmark_ret

            logger.info(f"组合总收益: {total_ret*100:+.2f}%")
            logger.info(f"基准总收益: {benchmark_ret*100:+.2f}%")
            logger.info(f"超额收益:   {excess_ret*100:+.2f}%")
            logger.info(f"平均持仓:   {df['n_stocks'].mean():.1f} 只")
            logger.info(f"交易成本:   {cost*100:.2f}% (双边)")

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
