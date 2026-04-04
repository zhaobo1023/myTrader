# -*- coding: utf-8 -*-
"""
因子选股器

核心逻辑:
1. 对每个因子做横截面百分位排名 (rank pct)
2. 根据 direction 翻转: direction=-1 时 score = 1 - pct
3. 加权合成 composite_score
4. 按合成得分选 Top N
"""

import logging

import numpy as np
import pandas as pd

from .config import (
    FACTOR_DEFS, FACTOR_DIRECTIONS, FACTOR_LABELS, FACTOR_GROUPS, DEFAULT_TOP_N,
    INDUSTRY_MAX_WEIGHT, INDUSTRY_CAP_ENABLED,
)

logger = logging.getLogger(__name__)


class FactorSelector:
    """多因子选股器"""

    def __init__(self, factors=None, weights=None, use_groups=False):
        """
        Args:
            factors: list of factor names, None = all factors
            weights: list of float, None = equal weight
            use_groups: if True, derive weights from FACTOR_GROUPS
        """
        if factors is None:
            if use_groups:
                factors = [f for g in FACTOR_GROUPS for f in g['factors']]
            else:
                factors = [f['name'] for f in FACTOR_DEFS]
        self.factors = factors

        if weights is None:
            if use_groups:
                # group-level equal weight, within-group equal weight
                weights = {}
                for g in FACTOR_GROUPS:
                    n = len(g['factors'])
                    w_per_factor = g['weight'] / n
                    for f in g['factors']:
                        weights[f] = w_per_factor
            else:
                weights = [1.0 / len(factors)] * len(factors)
                weights = dict(zip(factors, weights))
        else:
            total = sum(weights)
            weights = {f: w / total for f, w in zip(factors, weights)}
        self.weights = weights

    def _validate_factors(self, df):
        """Check which factors are available in the DataFrame."""
        available = [f for f in self.factors if f in df.columns]
        missing = [f for f in self.factors if f not in df.columns]
        if missing:
            logger.warning(f"Missing factors: {missing}")
        return available

    def score_cross_section(self, df: pd.DataFrame) -> pd.Series:
        """
        对单日横截面数据计算合成得分。

        Args:
            df: DataFrame, index=stock_code, columns=factor names

        Returns:
            Series, index=stock_code, values=composite_score
        """
        available = self._validate_factors(df)
        if not available:
            logger.warning("No factors available for scoring")
            return pd.Series(dtype=float)

        scores = pd.DataFrame(index=df.index)

        for f in available:
            direction = FACTOR_DIRECTIONS.get(f, 1)
            # 百分位排名: rank(pct=True) -> [0, 1]
            pct = df[f].rank(pct=True, ascending=True)
            if direction == -1:
                # 低值更好: 反转百分位
                scores[f] = 1.0 - pct
            else:
                scores[f] = pct
            scores[f] = scores[f].fillna(0.5)  # neutral for missing data

        # 去掉全 NaN 的因子列
        scores = scores.dropna(axis=1, how='all')

        # 加权合成
        w = {f: self.weights.get(f, 0) for f in scores.columns}
        w_total = sum(w.values())
        if w_total == 0:
            return pd.Series(dtype=float)

        composite = pd.Series(0.0, index=df.index)
        for f, weight in w.items():
            composite += scores[f] * weight
        composite /= w_total

        return composite

    def score_panel(self, panel: pd.DataFrame) -> pd.DataFrame:
        """
        对面板数据逐日计算合成得分。

        Args:
            panel: DataFrame with MultiIndex (trade_date, stock_code)

        Returns:
            DataFrame with column 'composite_score', same index as input
        """
        results = []
        dates = panel.index.get_level_values(0).unique().sort_values()

        for dt in dates:
            df_day = panel.loc[dt]
            if isinstance(df_day, pd.Series):
                # only one stock, skip
                continue
            scores = self.score_cross_section(df_day)
            if scores.empty:
                continue
            # attach trade_date as outer index level
            scores.index = pd.MultiIndex.from_tuples(
                [(dt, code) for code in scores.index],
                names=['trade_date', 'stock_code']
            )
            scores.name = 'composite_score'
            # 保留 trade_date 作为 index 的一层
            scores = scores.to_frame()
            scores.index.name = 'stock_code'
            scores['trade_date'] = dt
            results.append(scores)

        if not results:
            return pd.DataFrame()

        result = pd.concat(results).reset_index().set_index(['trade_date', 'stock_code'])
        return result[['composite_score']]

    def select_top_n(self, df: pd.DataFrame, top_n: int = DEFAULT_TOP_N,
                     min_price: float = 1.0, blacklist: set = None,
                     industry_map: dict = None,
                     industry_max_weight: float = INDUSTRY_MAX_WEIGHT) -> list:
        """
        从单日横截面选出 Top N 股票。

        Args:
            df: DataFrame, index=stock_code, columns include factor names + close_price
            top_n: number of stocks to select
            min_price: filter out stocks with price below this
            blacklist: set of stock_code to exclude (ST, newly listed, etc.)
            industry_map: dict {stock_code: industry_name} for industry cap
            industry_max_weight: max fraction of top_n per industry (e.g. 0.20 = 20%)

        Returns:
            list of stock_code
        """
        df_filtered = df

        # 黑名单过滤
        if blacklist:
            df_filtered = df_filtered[~df_filtered.index.isin(blacklist)]

        # 因子值过滤: 至少有一半因子非空
        factor_cols = [f for f in self.factors if f in df_filtered.columns]
        if factor_cols:
            valid_mask = df_filtered[factor_cols].notna().sum(axis=1) >= len(factor_cols) / 2
            df_filtered = df_filtered[valid_mask]

        # 基本面过滤: PB > 0, PE > 0 (排除亏损公司)
        for neg_filter_col in ('pb', 'pe_ttm'):
            if neg_filter_col in df_filtered.columns:
                df_filtered = df_filtered[df_filtered[neg_filter_col] > 0]

        if len(df_filtered) < top_n:
            logger.warning(f"Only {len(df_filtered)} stocks after filtering, requested {top_n}")
            top_n = len(df_filtered)

        if top_n == 0:
            return []

        scores = self.score_cross_section(df_filtered)

        # 按得分降序排列
        ranked = scores.sort_values(ascending=False)

        if INDUSTRY_CAP_ENABLED and industry_map:
            top_stocks = self._apply_industry_cap(
                ranked, top_n, industry_map, industry_max_weight
            )
        else:
            top_stocks = ranked.head(top_n).index.tolist()

        return top_stocks

    def _apply_industry_cap(self, ranked: pd.Series, top_n: int,
                            industry_map: dict,
                            max_weight: float) -> list:
        """
        行业权重上限: 限制每个行业最多占 top_n 的 max_weight。

        算法:
        1. 按得分降序遍历所有股票
        2. 跟踪每个行业已入选数量
        3. 当某行业已满时跳过该行业的后续股票
        4. 当选满 top_n 时停止

        Args:
            ranked: Series, index=stock_code, values=composite_score, 已降序排列
            top_n: 目标选股数
            industry_map: {stock_code: industry_name}
            max_weight: 单行业最大占比 (0.0 ~ 1.0)

        Returns:
            list of stock_code
        """
        industry_cap = max(1, int(top_n * max_weight))
        industry_count = {}
        selected = []

        for code in ranked.index:
            industry = industry_map.get(code)
            if industry is None:
                # 无行业数据的股票单独计数, 不受行业上限限制
                selected.append(code)
                if len(selected) >= top_n:
                    break
                continue

            count = industry_count.get(industry, 0)
            if count < industry_cap:
                selected.append(code)
                industry_count[industry] = count + 1
                if len(selected) >= top_n:
                    break

        # 统计
        if industry_count:
            top_industries = sorted(industry_count.items(), key=lambda x: -x[1])[:5]
            logger.info(f"  industry cap: max {industry_cap}/industry "
                        f"(top: {', '.join(f'{k}={v}' for k, v in top_industries)})")

        return selected

    def select_panel(self, panel: pd.DataFrame, top_n: int = DEFAULT_TOP_N,
                     rebalance_freq: int = 20, min_price: float = 1.0,
                     blacklist: set = None, industry_map: dict = None) -> pd.DataFrame:
        """
        面板回测选股: 按调仓频率定期选股。

        Args:
            panel: DataFrame with MultiIndex (trade_date, stock_code)
            top_n: stocks per rebalance
            rebalance_freq: rebalance every N trading days
            min_price: price filter

        Returns:
            DataFrame with columns [trade_date, stock_code, rank, composite_score]
        """
        dates = panel.index.get_level_values(0).unique().sort_values()
        all_selections = []
        rebalance_dates = dates.tolist()[::rebalance_freq]

        for i, dt in enumerate(rebalance_dates):
            df_day = panel.loc[dt]
            if isinstance(df_day, pd.Series):
                continue

            top_stocks = self.select_top_n(df_day, top_n=top_n, min_price=min_price,
                                           blacklist=blacklist, industry_map=industry_map)
            if not top_stocks:
                continue

            scores = self.score_cross_section(df_day)
            for rank, code in enumerate(top_stocks, 1):
                all_selections.append({
                    'trade_date': dt,
                    'stock_code': code,
                    'rank': rank,
                    'composite_score': scores.get(code, np.nan),
                })

            if (i + 1) % 10 == 0:
                logger.info(f"  Rebalance {i+1}/{len(rebalance_dates)}: {dt.strftime('%Y-%m-%d')}")

        if not all_selections:
            return pd.DataFrame()

        result = pd.DataFrame(all_selections)
        logger.info(f"Total selections: {len(result)} across {result['trade_date'].nunique()} rebalances")
        return result


def calc_backtest_returns(selections: pd.DataFrame,
                          daily_prices: pd.DataFrame) -> pd.DataFrame:
    """
    根据选股结果计算组合收益。

    Args:
        selections: DataFrame with [trade_date, stock_code, rank]
        daily_prices: DataFrame with MultiIndex (trade_date, stock_code), column close_price

    Returns:
        DataFrame with columns [trade_date, portfolio_return, benchmark_return, excess_return]
    """
    if selections.empty or daily_prices.empty:
        return pd.DataFrame()

    dates = selections['trade_date'].unique()
    dates = pd.to_datetime(sorted(dates))

    # 构建持仓期映射: 每个调仓日持有到下一个调仓日
    portfolio_returns = []

    for i in range(len(dates)):
        dt = dates[i]
        # 持仓结束日
        dt_end = dates[i + 1] if i + 1 < len(dates) else None

        # 选出的股票
        sel = selections[selections['trade_date'] == dt]
        codes = sel['stock_code'].tolist()

        if not codes:
            continue

        # 买入价: 调仓日收盘
        buy_prices = {}
        for code in codes:
            if (dt, code) in daily_prices.index:
                buy_prices[code] = daily_prices.loc[(dt, code), 'close_price']

        # 卖出价: 下一个调仓日收盘
        sell_prices = {}
        if dt_end is not None:
            for code in codes:
                if (dt_end, code) in daily_prices.index:
                    sell_prices[code] = daily_prices.loc[(dt_end, code), 'close_price']

        # 计算等权组合收益
        stock_returns = []
        for code in codes:
            if code in buy_prices and buy_prices[code] > 0:
                bp = float(buy_prices[code])
                if code in sell_prices and sell_prices[code] > 0:
                    sp = float(sell_prices[code])
                    stock_returns.append((sp / bp) - 1)
                # 如果没有卖出价(最后一段), 用当日收盘作为卖出
                else:
                    stock_returns.append(0.0)

        if stock_returns:
            portfolio_returns.append({
                'trade_date': dt,
                'portfolio_return': np.mean(stock_returns),
                'n_stocks': len(stock_returns),
            })

    if not portfolio_returns:
        return pd.DataFrame()

    result = pd.DataFrame(portfolio_returns)
    result['cumulative_return'] = (1 + result['portfolio_return']).cumprod() - 1
    return result
