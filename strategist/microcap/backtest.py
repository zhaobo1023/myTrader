# -*- coding: utf-8 -*-
"""
Microcap PEG 策略回测引擎

流程：
1. 按日期循环
2. 获取当日 universe
3. 计算因子值，百分位排名
4. 取因子排名最小的 top_n 个（PEG 越小越好）
5. T+1 买入，T+1+hold_days 卖出
6. 计算收益率
7. 累计净值
"""
import logging
import time
from typing import List, Dict, Optional
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

from config.db import get_connection
from .config import MicrocapConfig
from .universe import get_daily_universe
from .factors import calc_peg, calc_pe, calc_roe, calc_ebit_ratio, calc_peg_ebit_mv, calc_pure_mv

logger = logging.getLogger(__name__)


class MicrocapBacktest:
    """Microcap PEG 策略回测引擎"""

    def __init__(self, config: MicrocapConfig):
        """
        初始化回测引擎。

        Args:
            config: MicrocapConfig 配置对象
        """
        self.config = config
        self.trades = []           # 交易记录
        self.portfolio_values = [] # 净值记录
        self.holdings = {}         # 当前持仓 {stock_code: (buy_date, buy_price, units)}
        self._price_cache = {}     # 价格缓存 {trade_date: {'open': {code: price}, 'close': {code: price}}}

    def run(self) -> Dict:
        """
        执行回测。

        Returns:
            回测结果字典，包含：
            - status: 'ok' or 'error'
            - message: 状态消息
            - backtest_summary: 回测统计摘要
            - trades_df: 交易记录 DataFrame
            - daily_values_df: 每日净值 DataFrame
        """
        try:
            # 获取交易日列表
            trade_dates = self._get_trade_dates(
                self.config.start_date,
                self.config.end_date
            )
            logger.info(f"[OK] Loaded {len(trade_dates)} trading days")

            if len(trade_dates) < 2:
                logger.error("[ERROR] Insufficient trading days for backtest")
                return {
                    'status': 'error',
                    'message': 'Insufficient trading days',
                    'backtest_summary': {},
                    'trades_df': pd.DataFrame(),
                    'daily_values_df': pd.DataFrame(),
                }

            # 回测主循环
            cash = 1.0                     # 现金余额
            holdings = {}                  # 持仓 {stock_code: (buy_date, buy_price, units, sell_date)}
            daily_values = []
            pending_buy = None             # 待买入的选股 {date: [codes]}

            for i, trade_date in enumerate(trade_dates):
                # 第1步：处理卖出（持有期到期）—— 先卖后买，确保现金充足
                for code in list(holdings.keys()):
                    buy_date, buy_price, units, sell_date = holdings[code]
                    if trade_date == sell_date:
                        # 卖出：使用开盘价，向下滑点
                        sell_price_raw = self._get_open_price(code, trade_date)
                        if sell_price_raw is not None and sell_price_raw > 0:
                            sell_price = sell_price_raw * (1 - self.config.slippage_rate)
                            proceeds = units * sell_price * (1 - self.config.sell_cost_rate)
                            cash += proceeds
                            pnl = proceeds - (units * buy_price)
                            pnl_pct = (sell_price / buy_price - 1) - self.config.buy_cost_rate - self.config.sell_cost_rate

                            self.trades.append({
                                'buy_date': buy_date,
                                'sell_date': trade_date,
                                'stock_code': code,
                                'buy_price': buy_price,
                                'sell_price': sell_price,
                                'hold_days': self.config.hold_days,
                                'return': pnl_pct,
                                'pnl': pnl,
                            })

                            logger.debug(f"Sell {code} on {trade_date}: "
                                       f"buy={buy_price:.2f}, sell={sell_price:.2f}, "
                                       f"return={pnl_pct:.4f}")
                            del holdings[code]

                # 第2步：执行前一交易日的选股（T+1 买入）
                if pending_buy is not None:
                    selected_codes = pending_buy
                    pending_buy = None

                    if selected_codes and cash > 0:
                        # 只买入当前未持有的股票，避免覆盖已有仓位
                        new_codes = [c for c in selected_codes if c not in holdings]
                        buy_prices = {}
                        for code in new_codes:
                            # 买入：使用开盘价，向上滑点
                            price_raw = self._get_open_price(code, trade_date)
                            if price_raw is not None and price_raw > 0:
                                buy_prices[code] = price_raw * (1 + self.config.slippage_rate)

                        if buy_prices:
                            # 等权分配资金
                            per_stock_capital = cash / len(buy_prices)
                            for code, buy_price in buy_prices.items():
                                units = (per_stock_capital * (1 - self.config.buy_cost_rate)) / buy_price
                                buy_cost = units * buy_price
                                cash -= buy_cost

                                # 计算卖出日期（T+hold_days）
                                sell_idx = i + self.config.hold_days
                                sell_date = trade_dates[sell_idx] if sell_idx < len(trade_dates) else None

                                holdings[code] = (trade_date, buy_price, units, sell_date)
                                logger.debug(f"Buy {code} on {trade_date}: "
                                           f"price={buy_price:.2f}, units={units:.2f}")

                # 第3步：选股（当前交易日，明天 T+1 执行）
                if i < len(trade_dates) - 1:
                    selected = self._select_stocks(trade_date)
                    if selected:
                        pending_buy = selected

                # 第4步：计算组合价值
                nav = cash
                for code, (buy_date, buy_price, units, sell_date) in holdings.items():
                    current_price = self._get_close_price(code, trade_date)
                    if current_price is not None and current_price > 0:
                        nav += units * current_price

                daily_return = (nav / (daily_values[-1]['nav'] if daily_values else 1.0)) - 1

                daily_values.append({
                    'trade_date': trade_date,
                    'nav': nav,
                    'daily_return': daily_return,
                    'cumulative_return': nav - 1,
                    'cash': cash,
                    'n_holdings': len(holdings),
                })

                if (i + 1) % 50 == 0 or i == len(trade_dates) - 1:
                    logger.info(f"  Progress: {i+1}/{len(trade_dates)} "
                               f"({trade_date}), NAV={nav:.4f}, Holdings={len(holdings)}")

            # 生成结果
            trades_df = pd.DataFrame(self.trades) if self.trades else pd.DataFrame()
            daily_values_df = pd.DataFrame(daily_values)

            # 统计摘要
            summary = self._calc_summary(trades_df, daily_values_df)

            logger.info("[OK] Backtest completed successfully")
            return {
                'status': 'ok',
                'message': 'Backtest completed',
                'backtest_summary': summary,
                'trades_df': trades_df,
                'daily_values_df': daily_values_df,
            }

        except Exception as e:
            logger.error(f"[ERROR] Backtest failed: {e}", exc_info=True)
            return {
                'status': 'error',
                'message': str(e),
                'backtest_summary': {},
                'trades_df': pd.DataFrame(),
                'daily_values_df': pd.DataFrame(),
            }

    def _get_trade_dates(self, start_date: str, end_date: str) -> List[str]:
        """
        获取日期范围内的所有交易日。

        Args:
            start_date: 开始日期，格式 'YYYY-MM-DD'
            end_date: 结束日期，格式 'YYYY-MM-DD'

        Returns:
            交易日列表
        """
        conn = get_connection()
        try:
            sql = """
                SELECT DISTINCT trade_date
                FROM trade_stock_daily
                WHERE trade_date >= %s AND trade_date <= %s
                ORDER BY trade_date ASC
            """
            df = pd.read_sql(sql, conn, params=[start_date, end_date])
        finally:
            conn.close()

        dates = df['trade_date'].astype(str).tolist()
        logger.info(f"Found {len(dates)} trading days from {start_date} to {end_date}")
        return dates

    def _select_stocks(self, trade_date: str) -> List[str]:
        """
        在指定交易日选股。

        Args:
            trade_date: 选股日期

        Returns:
            选中的股票代码列表
        """
        try:
            # peg_ebit_mv 和 pure_mv 从全市场选股（不限市值）
            # 其余因子从市值后 percentile 的微盘股池中选
            FULL_MARKET_FACTORS = {'peg_ebit_mv', 'pure_mv'}

            if self.config.factor in FULL_MARKET_FACTORS:
                universe = get_daily_universe(
                    trade_date,
                    percentile=1.0,
                    exclude_st=self.config.exclude_st,
                    require_positive_pe=(self.config.factor != 'pure_mv'),
                )
            else:
                universe = get_daily_universe(
                    trade_date,
                    percentile=self.config.market_cap_percentile,
                    exclude_st=self.config.exclude_st,
                )

            if not universe:
                return []

            # 因子计算分发
            factor_funcs = {
                'peg':         calc_peg,
                'pe':          calc_pe,
                'roe':         calc_roe,
                'ebit_ratio':  calc_ebit_ratio,
                'peg_ebit_mv': calc_peg_ebit_mv,
                'pure_mv':     calc_pure_mv,
            }
            if self.config.factor not in factor_funcs:
                logger.warning(f"Unsupported factor: {self.config.factor}")
                return []
            factors_df = factor_funcs[self.config.factor](trade_date, universe)

            if factors_df.empty:
                return []

            # 选出因子值最小的 top_n 只
            factors_df = factors_df.dropna(subset=[self.config.factor])
            factors_df = factors_df.sort_values(self.config.factor)
            top_stocks = factors_df.head(self.config.top_n)['stock_code'].tolist()

            logger.debug(f"{trade_date}: selected {len(top_stocks)} stocks")

            return top_stocks

        except Exception as e:
            logger.warning(f"Error selecting stocks for {trade_date}: {e}")
            return []

    def _load_prices_for_date(self, trade_date: str) -> None:
        """批量加载指定日期所有股票的开盘价和收盘价到缓存，带重试。"""
        if trade_date in self._price_cache:
            return
        for attempt in range(3):
            try:
                conn = get_connection()
                try:
                    sql = """
                        SELECT stock_code, open_price, close_price FROM trade_stock_daily
                        WHERE trade_date = %s AND close_price > 0
                    """
                    df = pd.read_sql(sql, conn, params=[trade_date])
                    self._price_cache[trade_date] = {
                        'open':  dict(zip(df['stock_code'], df['open_price'].astype(float))),
                        'close': dict(zip(df['stock_code'], df['close_price'].astype(float))),
                    }
                    return
                finally:
                    conn.close()
            except Exception as e:
                if attempt < 2:
                    logger.warning(f"DB error on {trade_date} (attempt {attempt+1}/3): {e}, retrying...")
                    time.sleep(3)
                else:
                    logger.error(f"DB error on {trade_date} after 3 attempts: {e}")
                    self._price_cache[trade_date] = {'open': {}, 'close': {}}

    def _get_open_price(self, stock_code: str, trade_date: str) -> Optional[float]:
        """获取股票在指定交易日的开盘价（执行价）。"""
        self._load_prices_for_date(trade_date)
        price = self._price_cache[trade_date]['open'].get(stock_code)
        # 开盘价异常（停牌/一字板）时回退到收盘价
        if price is None or price <= 0:
            price = self._price_cache[trade_date]['close'].get(stock_code)
        return price

    def _get_close_price(self, stock_code: str, trade_date: str) -> Optional[float]:
        """获取股票在指定交易日的收盘价（估值/盯市用）。"""
        self._load_prices_for_date(trade_date)
        return self._price_cache[trade_date]['close'].get(stock_code)

    def _calc_summary(self, trades_df: pd.DataFrame,
                      daily_values_df: pd.DataFrame) -> Dict:
        """
        计算回测统计摘要。

        Args:
            trades_df: 交易记录 DataFrame
            daily_values_df: 每日净值 DataFrame

        Returns:
            统计摘要字典
        """
        summary = {
            'total_trades': int(len(trades_df)),
            'winning_trades': 0,
            'losing_trades': 0,
            'total_return': 0.0,
            'annual_return': 0.0,
            'sharpe_ratio': 0.0,
            'max_drawdown': 0.0,
            'win_rate': 0.0,
        }

        if trades_df.empty or daily_values_df.empty:
            return summary

        # 胜负统计
        winning = int((trades_df['return'] > 0).sum())
        losing = int((trades_df['return'] <= 0).sum())
        summary['winning_trades'] = winning
        summary['losing_trades'] = losing
        summary['win_rate'] = float(winning / len(trades_df)) if len(trades_df) > 0 else 0.0

        # 总收益
        final_nav = float(daily_values_df.iloc[-1]['nav']) if len(daily_values_df) > 0 else 1.0
        summary['total_return'] = float(final_nav - 1.0)

        # 年化收益
        n_days = len(daily_values_df)
        if n_days > 0:
            years = n_days / 250  # 250 交易日/年
            summary['annual_return'] = float((final_nav ** (1 / years)) - 1) if years > 0 else 0.0

        # 夏普比率
        if len(daily_values_df) > 1:
            daily_returns = daily_values_df['daily_return'].values
            if np.std(daily_returns) > 0:
                summary['sharpe_ratio'] = float(
                    np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(250)
                )

        # 最大回撤
        if len(daily_values_df) > 0:
            cummax = daily_values_df['nav'].cummax()
            drawdown = (daily_values_df['nav'] - cummax) / cummax
            summary['max_drawdown'] = float(drawdown.min())

        return summary
