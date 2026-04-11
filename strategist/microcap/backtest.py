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
from .benchmark import load_benchmark, calc_benchmark_metrics, DEFAULT_BENCHMARK

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
        self.holdings = {}         # 当前持仓 {stock_code: dict(buy_date, buy_price, units, sell_date, delay_count)}
        self._price_cache = {}     # 价格缓存 {trade_date: {'open','close','high','low': {code: price}}}
        self._prev_close: Dict[str, float] = {}   # 上一交易日收盘价 {code: price}，用于涨跌停判断
        self._trade_dates: List[str] = []          # 全量交易日列表（run() 时填充）
        self._date_to_idx: Dict[str, int] = {}     # 日期 -> 索引，O(1) 查找
        self._limit_up_skipped: int = 0            # 涨停跳过买入次数
        self._limit_down_delayed: int = 0          # 跌停顺延卖出次数
        self._delist_writeoffs: int = 0            # 退市归零笔数

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

            # 填充交易日索引（供涨跌停顺延使用）
            self._trade_dates = trade_dates
            self._date_to_idx = {d: i for i, d in enumerate(trade_dates)}

            # 预热 _prev_close：加载第一个交易日前一日的收盘价，确保第一天涨跌停判断有效
            pre_date = self._get_prev_trade_date(trade_dates[0])
            if pre_date:
                self._load_prices_for_date(pre_date)
                logger.info(f"[OK] Pre-warmed _prev_close with {len(self._prev_close)} stocks from {pre_date}")
            else:
                logger.warning("[WARN] Could not find pre-date for _prev_close warm-up; "
                               "limit-up/down checks on day 1 may be inaccurate")

            # 回测主循环
            cash = 1.0                     # 现金余额
            holdings = {}                  # 持仓 {stock_code: dict}
            daily_values = []
            pending_buy = None             # 待买入的选股 [codes]

            for i, trade_date in enumerate(trade_dates):
                # 第1步：处理卖出（持有期到期）—— 先卖后买，确保现金充足
                for code in list(holdings.keys()):
                    h = holdings[code]
                    if trade_date != h['sell_date']:
                        continue

                    # 检测一字跌停：无法成交，顺延最多 5 个交易日
                    if self._is_limit_down(code, trade_date) and h['delay_count'] < 5:
                        idx = self._date_to_idx[trade_date]
                        if idx + 1 < len(trade_dates):
                            h['sell_date'] = trade_dates[idx + 1]
                            h['delay_count'] += 1
                            self._limit_down_delayed += 1
                            logger.debug(f"Sell {code} delayed (limit-down) to {h['sell_date']}, "
                                         f"delay_count={h['delay_count']}")
                            continue
                        # 无后续交易日，强制按现价卖出（兜底）

                    # 卖出：使用开盘价，向下滑点
                    sell_price_raw = self._get_open_price(code, trade_date)
                    if sell_price_raw is not None and sell_price_raw > 0:
                        sell_price = sell_price_raw * (1 - self.config.slippage_rate)
                        units_held = h['units']
                        proceeds = units_held * sell_price * (1 - self.config.sell_cost_rate)
                        cash += proceeds
                        capital_invested = h.get('capital_invested', units_held * h['buy_price'])
                        pnl = proceeds - capital_invested
                        pnl_pct = proceeds / capital_invested - 1

                        self.trades.append({
                            'buy_date':  h['buy_date'],
                            'sell_date': trade_date,
                            'stock_code': code,
                            'buy_price':  h['buy_price'],
                            'sell_price': sell_price,
                            'hold_days':  self.config.hold_days + h['delay_count'],
                            'delay_count': h['delay_count'],
                            'return': pnl_pct,
                            'pnl': pnl,
                        })

                        logger.debug(f"Sell {code} on {trade_date}: "
                                     f"buy={h['buy_price']:.2f}, sell={sell_price:.2f}, "
                                     f"return={pnl_pct:.4f}, delay={h['delay_count']}")
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
                            # 一字涨停：无法买入，跳过
                            if self._is_limit_up(code, trade_date):
                                self._limit_up_skipped += 1
                                logger.debug(f"Buy {code} skipped (limit-up) on {trade_date}")
                                continue
                            # 买入：使用开盘价，向上滑点
                            price_raw = self._get_open_price(code, trade_date)
                            if price_raw is not None and price_raw > 0:
                                buy_prices[code] = price_raw * (1 + self.config.slippage_rate)

                        if buy_prices:
                            # 等权目标：每只股占总净值的 1/top_n
                            # 总净值用前一日 NAV（买入发生在 T+1 开盘，基准是昨日 NAV）
                            prev_nav = daily_values[-1]['nav'] if daily_values else 1.0
                            target_per_stock = prev_nav / max(len(selected_codes), 1)
                            # 将可用现金按新股数量均分，取两者中的较小值
                            available_per_new = cash / len(buy_prices)
                            for code, buy_price in buy_prices.items():
                                per_stock_capital = min(target_per_stock, available_per_new)
                                units = (per_stock_capital * (1 - self.config.buy_cost_rate)) / buy_price
                                actual_spent = per_stock_capital  # 每只新股实际花费（含手续费）
                                cash -= actual_spent

                                # 计算卖出日期（T+hold_days）
                                sell_idx = i + self.config.hold_days
                                sell_date = trade_dates[sell_idx] if sell_idx < len(trade_dates) else None

                                holdings[code] = {
                                    'buy_date':         trade_date,
                                    'buy_price':        buy_price,
                                    'units':            units,
                                    'capital_invested': actual_spent,  # 买入实际花费（含手续费）
                                    'sell_date':        sell_date,
                                    'delay_count':      0,
                                    'no_price_days':    0,   # 连续无收盘价天数（退市检测）
                                }
                                logger.debug(f"Buy {code} on {trade_date}: "
                                             f"price={buy_price:.2f}, units={units:.2f}, "
                                             f"capital={actual_spent:.4f}")

                # 第3步：选股（当前交易日，明天 T+1 执行）
                if i < len(trade_dates) - 1:
                    selected = self._select_stocks(trade_date)
                    if selected:
                        pending_buy = selected

                # 第4步：退市检测 + 计算组合价值
                # 持仓股连续 3 个交易日无收盘价 → 视为退市/暂停，按 0 价格强制平仓（归零）
                DELIST_THRESHOLD = 3
                for code in list(holdings.keys()):
                    h = holdings[code]
                    current_price = self._get_close_price(code, trade_date)
                    if current_price is None or current_price <= 0:
                        h['no_price_days'] += 1
                        if h['no_price_days'] >= DELIST_THRESHOLD:
                            # 归零：记录亏损 100%（含买入成本）
                            pnl_pct = -1.0 - self.config.buy_cost_rate  # 本金全亏 + 买入手续费
                            self.trades.append({
                                'buy_date':    h['buy_date'],
                                'sell_date':   trade_date,
                                'stock_code':  code,
                                'buy_price':   h['buy_price'],
                                'sell_price':  0.0,
                                'hold_days':   self.config.hold_days + h['delay_count'],
                                'delay_count': h['delay_count'],
                                'return':      pnl_pct,
                                'pnl':         -(h['units'] * h['buy_price']),
                                'delist':      True,
                            })
                            logger.warning(f"[DELIST] {code} has no price for {DELIST_THRESHOLD} days "
                                           f"as of {trade_date}, writing off position")
                            del holdings[code]
                    else:
                        h['no_price_days'] = 0  # 恢复计数

                nav = cash
                for code, h in holdings.items():
                    current_price = self._get_close_price(code, trade_date)
                    if current_price is not None and current_price > 0:
                        nav += h['units'] * current_price

                daily_return = (nav / (daily_values[-1]['nav'] if daily_values else 1.0)) - 1

                daily_values.append({
                    'trade_date': trade_date,
                    'nav': nav,
                    'daily_return': daily_return,
                    'cumulative_return': nav - 1,
                    'cash': cash,
                    'n_holdings': len(holdings),
                })

                # 最后一个交易日：强制按收盘价平仓 sell_date=None 的持仓（持有期超出回测范围）
                if i == len(trade_dates) - 1:
                    for code in list(holdings.keys()):
                        h = holdings[code]
                        if h['sell_date'] is not None:
                            continue
                        close_price = self._get_close_price(code, trade_date)
                        if close_price is not None and close_price > 0:
                            sell_price = close_price * (1 - self.config.slippage_rate)
                            units_held = h['units']
                            proceeds = units_held * sell_price * (1 - self.config.sell_cost_rate)
                            cash += proceeds
                            capital_invested = h.get('capital_invested', units_held * h['buy_price'])
                            pnl = proceeds - capital_invested
                            pnl_pct = proceeds / capital_invested - 1
                            self.trades.append({
                                'buy_date':    h['buy_date'],
                                'sell_date':   trade_date,
                                'stock_code':  code,
                                'buy_price':   h['buy_price'],
                                'sell_price':  sell_price,
                                'hold_days':   self.config.hold_days + h['delay_count'],
                                'delay_count': h['delay_count'],
                                'return':      pnl_pct,
                                'pnl':         pnl,
                                'forced_close': True,
                            })
                            logger.debug(f"[FORCE CLOSE] {code} on {trade_date}: "
                                         f"sell={sell_price:.2f}, return={pnl_pct:.4f}")
                            del holdings[code]

                # 全市场因子每天 SQL 开销大，每 10 天打一次日志；其余因子每 50 天
                FULL_MARKET_FACTORS = {'peg_ebit_mv', 'pure_mv'}
                log_interval = 10 if self.config.factor in FULL_MARKET_FACTORS else 50
                if (i + 1) % log_interval == 0 or i == len(trade_dates) - 1:
                    logger.info(f"  Progress: {i+1}/{len(trade_dates)} "
                               f"({trade_date}), NAV={nav:.4f}, Holdings={len(holdings)}")

            # 生成结果
            trades_df = pd.DataFrame(self.trades) if self.trades else pd.DataFrame()
            daily_values_df = pd.DataFrame(daily_values)

            # 加载基准数据（可选）
            benchmark_df = pd.DataFrame()
            if self.config.benchmark_code:
                benchmark_df = load_benchmark(
                    self.config.benchmark_code,
                    self.config.start_date,
                    self.config.end_date,
                )

            # 统计摘要
            summary = self._calc_summary(trades_df, daily_values_df, benchmark_df)

            logger.info("[OK] Backtest completed successfully")
            return {
                'status': 'ok',
                'message': 'Backtest completed',
                'backtest_summary': summary,
                'trades_df': trades_df,
                'daily_values_df': daily_values_df,
                'benchmark_df': benchmark_df,
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

    def _get_prev_trade_date(self, trade_date: str) -> Optional[str]:
        """
        查询给定日期前一个交易日。

        Args:
            trade_date: 基准日期，格式 'YYYY-MM-DD'

        Returns:
            前一个交易日字符串，若不存在则返回 None
        """
        conn = get_connection()
        try:
            sql = """
                SELECT DISTINCT trade_date
                FROM trade_stock_daily
                WHERE trade_date < %s
                ORDER BY trade_date DESC
                LIMIT 1
            """
            df = pd.read_sql(sql, conn, params=[trade_date])
        finally:
            conn.close()

        if df.empty:
            return None
        return str(df.iloc[0]['trade_date'])

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
                    min_avg_turnover=self.config.min_avg_turnover,
                )
            else:
                universe = get_daily_universe(
                    trade_date,
                    percentile=self.config.market_cap_percentile,
                    exclude_st=self.config.exclude_st,
                    min_avg_turnover=self.config.min_avg_turnover,
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
        """批量加载指定日期所有股票的开盘/收盘/最高/最低价到缓存，带重试。
        同步更新 _prev_close（用于涨跌停判断）。
        """
        if trade_date in self._price_cache:
            return
        for attempt in range(3):
            try:
                conn = get_connection()
                try:
                    sql = """
                        SELECT stock_code, open_price, high_price, low_price, close_price
                        FROM trade_stock_daily
                        WHERE trade_date = %s AND close_price > 0
                    """
                    df = pd.read_sql(sql, conn, params=[trade_date])
                    close_dict = dict(zip(df['stock_code'], df['close_price'].astype(float)))
                    self._price_cache[trade_date] = {
                        'open':  dict(zip(df['stock_code'], df['open_price'].astype(float))),
                        'high':  dict(zip(df['stock_code'], df['high_price'].astype(float))),
                        'low':   dict(zip(df['stock_code'], df['low_price'].astype(float))),
                        'close': close_dict,
                    }
                    # 当前日期加载完毕后，_prev_close 更新为本日收盘
                    # （下次加载更晚日期时使用）
                    self._prev_close.update(close_dict)
                    return
                finally:
                    conn.close()
            except Exception as e:
                if attempt < 2:
                    logger.warning(f"DB error on {trade_date} (attempt {attempt+1}/3): {e}, retrying...")
                    time.sleep(3)
                else:
                    logger.error(f"DB error on {trade_date} after 3 attempts: {e}")
                    self._price_cache[trade_date] = {'open': {}, 'high': {}, 'low': {}, 'close': {}}

    def _is_limit_down(self, stock_code: str, trade_date: str) -> bool:
        """判断股票在指定交易日是否一字跌停（无法卖出）。
        判断逻辑：high == low（一字板） AND 相对前收盘跌幅 <= -4%。
        -4% 阈值同时覆盖普通股 -10% 和 ST -5% 的跌停情形。
        """
        self._load_prices_for_date(trade_date)
        cache = self._price_cache[trade_date]
        high = cache['high'].get(stock_code)
        low  = cache['low'].get(stock_code)
        close = cache['close'].get(stock_code)
        prev_close = self._prev_close.get(stock_code)

        if high is None or low is None or close is None or prev_close is None or prev_close <= 0:
            return False
        if abs(high - low) > 0.001:   # 非一字板：有正常价格区间
            return False
        pct_chg = (close - prev_close) / prev_close
        return pct_chg <= -0.04

    def _is_limit_up(self, stock_code: str, trade_date: str) -> bool:
        """判断股票在指定交易日是否一字涨停（无法买入）。
        判断逻辑：high == low（一字板） AND 相对前收盘涨幅 >= +4%。
        """
        self._load_prices_for_date(trade_date)
        cache = self._price_cache[trade_date]
        high = cache['high'].get(stock_code)
        low  = cache['low'].get(stock_code)
        close = cache['close'].get(stock_code)
        prev_close = self._prev_close.get(stock_code)

        if high is None or low is None or close is None or prev_close is None or prev_close <= 0:
            return False
        if abs(high - low) > 0.001:
            return False
        pct_chg = (close - prev_close) / prev_close
        return pct_chg >= 0.04

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
                      daily_values_df: pd.DataFrame,
                      benchmark_df: pd.DataFrame = None) -> Dict:
        """
        计算回测统计摘要（含基准对比指标）。

        Args:
            trades_df: 交易记录 DataFrame
            daily_values_df: 每日净值 DataFrame
            benchmark_df: 基准日线 DataFrame（可选），列含 trade_date / daily_return

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
            'limit_up_skipped': self._limit_up_skipped,
            'limit_down_delayed': self._limit_down_delayed,
            'delist_writeoffs': self._delist_writeoffs,
            # 基准指标（默认空值，有基准数据时填充）
            'benchmark_code': self.config.benchmark_code,
            'benchmark_annual_return': None,
            'excess_annual_return': None,
            'information_ratio': None,
            'beta': None,
            'alpha': None,
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

        # 基准对比指标
        if benchmark_df is not None and not benchmark_df.empty and len(daily_values_df) > 1:
            strat_series = daily_values_df.set_index('trade_date')['daily_return']
            bench_series = benchmark_df.set_index('trade_date')['daily_return']
            bench_metrics = calc_benchmark_metrics(strat_series, bench_series)
            summary.update(bench_metrics)

        return summary
