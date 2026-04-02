# -*- coding: utf-8 -*-
"""
收益率矩阵构建 - 数据加载 + 预处理 + 停牌过滤 + 行业中性化
"""
import sys
import os
import logging
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config.db import execute_query
from .config import SVDMonitorConfig

logger = logging.getLogger(__name__)


class DataBuilder:
    """收益率矩阵构建器"""

    def __init__(self, config: SVDMonitorConfig = None):
        self.config = config or SVDMonitorConfig()
        self._industry_map: dict = None  # 延迟加载 + 缓存

    # ================================================================
    # 数据加载
    # ================================================================

    def load_returns(self, start_date: str, end_date: str,
                     stock_codes: list = None) -> pd.DataFrame:
        """
        从数据库加载日收益率矩阵

        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            stock_codes: 可选，指定股票子集 (用于行业 SVD)

        Returns:
            DataFrame: index=trade_date, columns=stock_code, values=return
        """
        max_window = max(self.config.windows.keys())
        extended_start = self._subtract_trading_days(start_date, max_window + 10)

        if stock_codes:
            # 指定股票子集: 使用 IN 查询
            placeholders = ','.join(['%s'] * len(stock_codes))
            sql = f"""
                SELECT stock_code, trade_date, close_price, volume
                FROM trade_stock_daily
                WHERE trade_date >= %s AND trade_date <= %s
                  AND stock_code IN ({placeholders})
                ORDER BY stock_code, trade_date ASC
            """
            params = [extended_start, end_date] + list(stock_codes)
        else:
            sql = """
                SELECT stock_code, trade_date, close_price, volume
                FROM trade_stock_daily
                WHERE trade_date >= %s AND trade_date <= %s
                ORDER BY stock_code, trade_date ASC
            """
            params = [extended_start, end_date]

        rows = execute_query(sql, params)

        if not rows:
            raise ValueError(f"未加载到数据: {extended_start} ~ {end_date}")

        df = pd.DataFrame(rows)
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df['close_price'] = pd.to_numeric(df['close_price'], errors='coerce')
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce')

        # Pivot: index=trade_date, columns=stock_code, values=close_price
        price_df = df.pivot(index='trade_date', columns='stock_code', values='close_price')
        price_df = price_df.sort_index()

        # 计算收益率 (fill_method=None 避免前向填充停牌价格)
        returns_df = price_df.pct_change(fill_method=None)

        # 处理 inf 值 (涨停/跌停后一字板产生的 inf)
        returns_df = returns_df.replace([np.inf, -np.inf], np.nan)

        # 仅保留目标日期范围
        target_start = pd.Timestamp(start_date)
        returns_df = returns_df.loc[target_start:]

        logger.info(f"加载收益率矩阵: {returns_df.shape[0]} 天 x {returns_df.shape[1]} 只股票"
                     + (f" (子集)" if stock_codes else ""))
        return returns_df

    def load_industry_map(self) -> dict:
        """加载股票-行业映射 (带缓存)"""
        if self._industry_map is not None:
            return self._industry_map

        try:
            rows = execute_query(
                "SELECT stock_code, industry_name FROM trade_stock_industry"
            )
            self._industry_map = {
                r['stock_code']: r['industry_name']
                for r in rows if r.get('industry_name')
            }
            logger.info(f"加载行业映射: {len(self._industry_map)} 只股票")
            return self._industry_map
        except Exception as e:
            logger.warning(f"行业数据加载失败: {e}")
            self._industry_map = {}
            return {}

    def load_industry_stocks(self) -> dict:
        """
        加载申万一级行业 -> 股票列表映射

        Returns:
            dict: {行业名: [stock_code, ...]}
        """
        industry_map = self.load_industry_map()
        industry_stocks = {}
        for stock_code, industry_name in industry_map.items():
            industry_stocks.setdefault(industry_name, []).append(stock_code)
        return industry_stocks

    # ================================================================
    # 窗口矩阵构建
    # ================================================================

    def build_window_matrix(self, returns_df: pd.DataFrame,
                            start_idx: int, window_size: int,
                            stock_subset: list = None) -> tuple:
        """
        构建单个窗口的预处理后矩阵

        预处理流水线:
        - 默认模式: 停牌过滤 + fillna(0) + 行去均值 (最小预处理)
        - 行业中性化: fillna(0) + MAD + Z-Score + LinearRegression行业中性化 + 重新Z-Score + 行去均值

        Args:
            returns_df: 全量收益率 DataFrame (index=trade_date, columns=stock_code)
            start_idx: 窗口起始索引
            window_size: 窗口大小
            stock_subset: 可选，指定股票子集列 (用于行业 SVD)

        Returns:
            (processed_matrix, stock_count, valid_stocks)
        """
        window_data = returns_df.iloc[start_idx:start_idx + window_size]

        if len(window_data) < window_size:
            return None, 0, []

        # 可选: 只取子集股票
        if stock_subset:
            available = [s for s in stock_subset if s in window_data.columns]
            if available:
                window_data = window_data[available]

        # 1. 停牌/僵尸股过滤
        min_valid = int(window_size * self.config.min_valid_days_ratio)
        valid_mask = window_data.notna().sum(axis=0) >= min_valid
        valid_stocks = window_data.columns[valid_mask]

        if len(valid_stocks) < self.config.min_stock_count:
            logger.warning(
                f"窗口有效股票不足: {len(valid_stocks)} < {self.config.min_stock_count}, 跳过"
            )
            return None, 0, []

        window_filtered = window_data[valid_stocks].copy()

        # 2. 停牌日设为 0
        window_filtered = window_filtered.fillna(0)

        if self.config.industry_neutral:
            # 行业中性化模式
            window_filtered = self._mad_winsorize(window_filtered)
            window_filtered = self._zscore_standardize(window_filtered)
            window_filtered = self._industry_neutralize_lr(window_filtered)
            window_filtered = self._zscore_standardize(window_filtered)

        # 转置为 (stocks x days) 并去均值
        matrix = window_filtered.values.T  # (stocks, days)
        matrix = matrix - matrix.mean(axis=1, keepdims=True)

        return matrix, len(valid_stocks), list(valid_stocks)

    # ================================================================
    # 预处理方法
    # ================================================================

    def _mad_winsorize(self, df: pd.DataFrame) -> pd.DataFrame:
        """MAD 去极值: per stock across dates"""
        median = df.median(axis=0)
        mad = (df - median).abs().median(axis=0)
        mad = mad.replace(0, 1e-8)
        upper = median + self.config.mad_n * 1.4826 * mad
        lower = median - self.config.mad_n * 1.4826 * mad
        return df.clip(lower, upper, axis=0)

    def _zscore_standardize(self, df: pd.DataFrame) -> pd.DataFrame:
        """时序 Z-Score 标准化 (per stock across dates)"""
        mean = df.mean(axis=0)
        std = df.std(axis=0)
        std = std.replace(0, 1e-8)
        return (df - mean) / std

    def _industry_neutralize_lr(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        行业中性化: LinearRegression 哑变量回归取残差

        对每个截面 (每个交易日):
            y = stock returns (N x 1)
            X = industry dummy variables (N x K)
            residual = y - X @ beta

        残差代表去除行业效应后的个股超额收益。
        """
        from sklearn.linear_model import LinearRegression

        try:
            industry_map = self.load_industry_map()
            if not industry_map:
                logger.warning("行业数据为空，跳过行业中性化")
                return df

            stocks = list(df.columns)
            industries = pd.Series(
                [industry_map.get(s, None) for s in stocks], index=stocks
            )

            # 只保留有行业标签的股票
            valid_mask = industries.notna()
            valid_stocks = stocks  # 保留所有列，未知行业不参与回归

            # 构建行业哑变量矩阵
            unique_industries = sorted(industries.dropna().unique())
            if len(unique_industries) < 2:
                logger.warning("行业数量不足，跳过行业中性化")
                return df

            # 哑变量: N stocks x K industries
            dummy_matrix = np.zeros((len(stocks), len(unique_industries)))
            ind_to_idx = {ind: i for i, ind in enumerate(unique_industries)}
            for i, s in enumerate(stocks):
                ind = industries.get(s)
                if ind and ind in ind_to_idx:
                    dummy_matrix[i, ind_to_idx[ind]] = 1.0

            result = df.copy().values  # (T days, N stocks)

            # 逐日截面回归
            lr = LinearRegression(fit_intercept=True)
            for t in range(df.shape[0]):
                y = df.iloc[t].values.astype(float)
                X = dummy_matrix

                # 只用有行业标签的样本回归
                labeled_mask = np.array([industries.get(s) is not None for s in stocks])
                if labeled_mask.sum() < len(unique_industries) + 5:
                    continue

                try:
                    lr.fit(X[labeled_mask], y[labeled_mask])
                    fitted = lr.predict(X)
                    # 取残差: 只有有标签的股票替换为残差
                    residuals = y - fitted
                    result[t, labeled_mask] = residuals[labeled_mask]
                except Exception:
                    continue

            return pd.DataFrame(result, index=df.index, columns=df.columns)

        except ImportError:
            logger.warning("sklearn 未安装，跳过行业中性化")
            return df
        except Exception as e:
            logger.warning(f"行业中性化失败: {e}, 跳过")
            return df

    # ================================================================
    # 工具方法
    # ================================================================

    def _subtract_trading_days(self, date_str: str, n_days: int) -> str:
        """从日期往前减去约 n_days 个交易日 (粗估: 交易日/自然日 ≈ 5/7)"""
        from datetime import datetime, timedelta
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        natural_days = int(n_days * 7 / 5)
        extended = dt - timedelta(days=natural_days)
        return extended.strftime('%Y-%m-%d')
