# -*- coding: utf-8 -*-
"""
收益率矩阵构建 - 数据加载 + 预处理 + 停牌过滤
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

    def load_returns(self, start_date: str, end_date: str) -> pd.DataFrame:
        """
        从数据库加载全 A 股日收益率矩阵

        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            DataFrame: index=trade_date, columns=stock_code, values=close_price
        """
        # 需要额外加载 start_date 之前的数据用于计算首日收益率
        max_window = max(self.config.windows.keys())
        extended_start = self._subtract_trading_days(start_date, max_window + 10)

        sql = """
            SELECT stock_code, trade_date, close_price, volume
            FROM trade_stock_daily
            WHERE trade_date >= %s AND trade_date <= %s
            ORDER BY stock_code, trade_date ASC
        """
        rows = execute_query(sql, [extended_start, end_date])

        if not rows:
            raise ValueError(f"未加载到数据: {extended_start} ~ {end_date}")

        df = pd.DataFrame(rows)
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df['close_price'] = pd.to_numeric(df['close_price'], errors='coerce')
        df['volume'] = pd.to_numeric(df['volume'], errors='coerce')

        # Pivot: index=trade_date, columns=stock_code, values=close_price
        price_df = df.pivot(index='trade_date', columns='stock_code', values='close_price')
        price_df = price_df.sort_index()

        # 计算收益率
        returns_df = price_df.pct_change()

        # 处理 inf 值 (涨停/跌停后一字板产生的 inf)
        returns_df = returns_df.replace([np.inf, -np.inf], np.nan)

        # 仅保留目标日期范围
        target_start = pd.Timestamp(start_date)
        returns_df = returns_df.loc[target_start:]

        logger.info(f"加载收益率矩阵: {returns_df.shape[0]} 天 x {returns_df.shape[1]} 只股票")
        return returns_df

    def build_window_matrix(self, returns_df: pd.DataFrame,
                            start_idx: int, window_size: int) -> tuple:
        """
        构建单个窗口的预处理后矩阵

        Args:
            returns_df: 全量收益率 DataFrame
            start_idx: 窗口起始索引
            window_size: 窗口大小

        Returns:
            (processed_matrix, stock_count, valid_stocks)
            processed_matrix: numpy array (stocks x days), 已去均值
            stock_count: 有效股票数
        """
        window_data = returns_df.iloc[start_idx:start_idx + window_size]

        if len(window_data) < window_size:
            return None, 0, []

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

        # 2. 停牌日设为 0 (代表无超额波动)
        window_filtered = window_filtered.fillna(0)

        # 3. MAD 去极值 (截面)
        window_filtered = self._mad_winsorize(window_filtered)

        # 4. Z-Score 截面标准化
        window_filtered = self._zscore_cross_section(window_filtered)

        # 5. [可选] 行业中性化
        if self.config.industry_neutral:
            window_filtered = self._industry_neutralize(window_filtered)
            # 中性化后必须重新 Z-Score 标准化
            window_filtered = self._zscore_cross_section(window_filtered)

        # 转置为 (stocks x days) 并去均值
        matrix = window_filtered.values.T  # (stocks, days)
        matrix = matrix - matrix.mean(axis=1, keepdims=True)

        return matrix, len(valid_stocks), list(valid_stocks)

    def _mad_winsorize(self, df: pd.DataFrame) -> pd.DataFrame:
        """MAD 去极值: ±n*MAD 截断"""
        median = df.median(axis=0)
        mad = (df - median).abs().median(axis=0)
        mad = mad.replace(0, 1e-8)  # 防止除零
        upper = median + self.config.mad_n * 1.4826 * mad
        lower = median - self.config.mad_n * 1.4826 * mad
        return df.clip(lower, upper, axis=0)

    def _zscore_cross_section(self, df: pd.DataFrame) -> pd.DataFrame:
        """截面 Z-Score 标准化"""
        mean = df.mean(axis=0)
        std = df.std(axis=0)
        std = std.replace(0, 1e-8)  # 防止除零
        return (df - mean) / std

    def _industry_neutralize(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        行业中性化: 申万一级行业哑变量回归取残差
        使用简单方法: 每日截面减去行业均值
        """
        try:
            industry_map = self._load_industry_map()
            if not industry_map:
                logger.warning("行业数据加载失败，跳过行业中性化")
                return df

            stocks = df.columns
            industries = pd.Series([industry_map.get(s, 'unknown') for s in stocks],
                                   index=stocks)

            result = df.copy()
            for date_idx in df.index:
                row = df.loc[date_idx]
                for ind_name in industries.unique():
                    if ind_name == 'unknown':
                        continue
                    mask = industries == ind_name
                    ind_stocks = mask[mask].index
                    if len(ind_stocks) < 3:
                        continue
                    ind_mean = row[ind_stocks].mean()
                    result.loc[date_idx, ind_stocks] = row[ind_stocks] - ind_mean

            return result

        except Exception as e:
            logger.warning(f"行业中性化失败: {e}, 跳过")
            return df

    def _load_industry_map(self) -> dict:
        """加载股票-行业映射"""
        try:
            rows = execute_query(
                "SELECT stock_code, industry_name FROM trade_stock_industry"
            )
            return {r['stock_code']: r['industry_name'] for r in rows if r.get('industry_name')}
        except Exception:
            return {}

    def _subtract_trading_days(self, date_str: str, n_days: int) -> str:
        """从日期往前减去约 n_days 个交易日 (粗估: 交易日/自然日 ≈ 5/7)"""
        from datetime import datetime, timedelta
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        natural_days = int(n_days * 7 / 5)
        extended = dt - timedelta(days=natural_days)
        return extended.strftime('%Y-%m-%d')
