# -*- coding: utf-8 -*-
"""
截面预处理模块

实现两种预处理方法：
1. MAD 去极值 + Z-Score 标准化 (华泰标准)
2. RobustZScoreNorm (MASTER 论文)
"""
import numpy as np
import pandas as pd
from typing import List, Optional


class Preprocessor:
    """截面预处理器"""

    def __init__(self, method='mad', mad_multiplier=5.0, clip_range=3.0):
        """
        初始化预处理器

        参数:
            method: 'mad' 或 'robust_zscore'
            mad_multiplier: MAD 去极值倍数
            clip_range: RobustZScore 裁剪范围
        """
        self.method = method
        self.mad_multiplier = mad_multiplier
        self.clip_range = clip_range

    def robust_zscore_norm(self, series, clip_range=None):
        """
        MASTER 论文的 RobustZScoreNorm

        步骤:
          1. 计算中位数(median)和MAD(median absolute deviation)
          2. 鲁棒标准差 = MAD * 1.4826  (正态分布下MAD与标准差的换算)
          3. 标准化: (x - median) / robust_std
          4. 裁剪到 [-clip_range, clip_range]

        优势: 中位数和MAD对异常值免疫(高breakdown point)
        """
        if clip_range is None:
            clip_range = self.clip_range

        median = np.nanmedian(series)
        mad = np.nanmedian(np.abs(series - median))
        robust_std = mad * 1.4826

        if robust_std < 1e-10:
            return np.zeros_like(series)

        normalized = (series - median) / robust_std
        return np.clip(normalized, -clip_range, clip_range)

    def mad_zscore(self, series):
        """
        MAD 去极值 + Z-Score 标准化 (华泰标准)

        步骤:
          1. MAD 去极值: 中位数 +/- mad_multiplier*MAD 截断
          2. 缺失值填充: 列中位数
          3. Z-score 标准化: (x - mean) / std
        """
        # MAD 去极值
        median = series.median()
        mad = (series - median).abs().median()
        # 使用 1e-8 阈值避免 MAD=0 的边界情况
        if mad < 1e-8:
            return series - median
        upper = median + self.mad_multiplier * 1.4826 * mad
        lower = median - self.mad_multiplier * 1.4826 * mad
        series = series.clip(lower=lower, upper=upper)

        # 填充缺失值
        fill_val = series.median()
        series = series.fillna(fill_val)

        # Z-Score 标准化
        mean = series.mean()
        std = series.std()
        if std < 1e-8:
            return series - mean
        return (series - mean) / std

    def preprocess_features(self, df, feature_cols=None):
        """
        预处理特征（时间序列方式）

        参数:
            df: DataFrame
            feature_cols: 要处理的列名列表（None则自动检测）

        返回:
            DataFrame, 预处理后
        """
        df = df.copy()

        if feature_cols is None:
            from .feature_engine import get_all_feature_cols
            feature_cols = get_all_feature_cols()
            feature_cols = [c for c in feature_cols if c in df.columns]

        for col in feature_cols:
            series = df[col].copy()

            if self.method == 'mad':
                df[col] = self.mad_zscore(series)
            elif self.method == 'robust_zscore':
                vals = series.values.astype(float)
                df[col] = self.robust_zscore_norm(vals)
            else:
                raise ValueError(f"未知的预处理方法: {self.method}")

        return df

    def preprocess_cross_section(self, all_data, feature_cols):
        """
        截面预处理: 逐日截面标准化，每一天只用当天的截面数据计算统计量
        绝对不能用全局统计量

        参数:
            all_data: DataFrame, 必须含 'trade_date' 列和 feature_cols 中的列
            feature_cols: 特征列名列表

        返回:
            DataFrame, 预处理后
        """
        result = all_data.copy()

        for date, group in result.groupby('trade_date'):
            for col in feature_cols:
                if col not in group.columns:
                    continue
                series = group[col].copy()

                if self.method == 'mad':
                    series = self.mad_zscore(series)

                elif self.method == 'robust_zscore':
                    vals = series.values.astype(float)
                    series = pd.Series(
                        self.robust_zscore_norm(vals),
                        index=series.index
                    )

                result.loc[group.index, col] = series

        return result

    def preprocess_panel(self, df, feature_cols):
        """
        截面预处理的向量化版本（等价于 preprocess_cross_section，但更快）

        参数:
            df: DataFrame, 必须含 'trade_date' 列和 feature_cols 中的列
            feature_cols: 特征列名列表

        返回:
            DataFrame, 预处理后
        """
        df = df.copy()
        for col in feature_cols:
            if col not in df.columns:
                continue
            df[col] = df.groupby('trade_date')[col].transform(self.mad_zscore)
        return df

    def neutralize(self, factor_series, industry_dummies, mktcap_log=None):
        """
        行业市值中性化 (回归取残差)

        原理: factor = beta0 + beta_industry * industry + beta_mktcap * ln(mktcap) + residual
        残差residual就是中性化后的因子值

        参数:
            factor_series: Series, 单个因子值
            industry_dummies: DataFrame, 行业哑变量 (one-hot)
            mktcap_log: Series, 市值对数 (可选)

        返回:
            Series, 中性化后的因子值
        """
        from sklearn.linear_model import LinearRegression

        valid_mask = factor_series.notna()
        if valid_mask.sum() < 10:
            return factor_series

        X_parts = [industry_dummies.loc[valid_mask]]
        if mktcap_log is not None:
            X_parts.append(mktcap_log.loc[valid_mask].to_frame('mktcap'))

        X = pd.concat(X_parts, axis=1).fillna(0)
        y = factor_series.loc[valid_mask].values

        model = LinearRegression()
        model.fit(X.values, y)
        residual = y - model.predict(X.values)

        result = factor_series.copy()
        result.loc[valid_mask] = residual
        return result
