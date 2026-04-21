# -*- coding: utf-8 -*-
"""
数据加载模块

通过 DataFeed 接口加载股票数据并计算因子，替代原始的 MySQL 直连方式。
"""
import pandas as pd
import numpy as np
from typing import List, Optional
import logging

from data.interface import DataFeed
from .feature_engine import FeatureEngine, get_all_feature_cols
from .preprocessor import Preprocessor
from .config import StrategyConfig

logger = logging.getLogger(__name__)


class DataLoader:
    """数据加载器"""

    def __init__(self, data_feed: DataFeed, config: StrategyConfig = None):
        """
        初始化数据加载器

        参数:
            data_feed: 数据源接口实现（如 CSVDataFeed）
            config: 策略配置
        """
        self.data_feed = data_feed
        self.config = config or StrategyConfig()
        self.feature_engine = FeatureEngine()
        self.preprocessor = Preprocessor(
            method=self.config.preprocess_method,
            mad_multiplier=self.config.mad_multiplier,
            clip_range=self.config.clip_range,
        )

    def load_and_compute_factors(
        self,
        stock_pool: List[str] = None,
        start_date: str = None,
        end_date: str = None,
    ) -> tuple:
        """
        加载股票数据并计算因子

        参数:
            stock_pool: 股票池列表
            start_date: 开始日期
            end_date: 结束日期

        返回:
            (panel, feature_cols)
        """
        if stock_pool is None:
            stock_pool = self.config.stock_pool
        if start_date is None:
            start_date = self.config.start_date
        if end_date is None:
            end_date = self.config.end_date

        logger.info("=" * 60)
        logger.info("加载数据并计算因子")
        logger.info("=" * 60)
        logger.info(f"股票池: {len(stock_pool)} 只")
        logger.info(f"日期范围: {start_date} ~ {end_date}")

        all_frames = []
        loaded = 0

        for i, code in enumerate(stock_pool, 1):
            try:
                df = self.data_feed.load_single_stock(code, start_date, end_date)
                if len(df) < self.config.min_bars:
                    logger.debug(f"[{i}/{len(stock_pool)}] {code}: 数据不足 ({len(df)} < {self.config.min_bars})")
                    continue

                # Step 1: 只计算技术因子（不含 future_ret）
                feat_df = self.feature_engine.calc_features(df)

                feat_df['stock_code'] = code
                feat_df['trade_date'] = feat_df.index

                all_frames.append(feat_df)
                loaded += 1

                if loaded % 10 == 0:
                    logger.info(f"进度: {loaded}/{len(stock_pool)}")

            except Exception as e:
                logger.error(f"[{i}/{len(stock_pool)}] {code}: 加载失败 - {e}")

        logger.info(f"\n成功加载: {loaded}/{len(stock_pool)} 只")

        if loaded < 10:
            raise ValueError("有效股票不足10只，无法进行截面分析")

        # Step 2: 合并数据
        panel = pd.concat(all_frames, ignore_index=True)

        # 获取特征列（排除价格列和标识列）
        feature_cols = get_all_feature_cols()
        feature_cols = [c for c in feature_cols if c in panel.columns]

        # Step 3: 先做截面预处理（此时 panel 里没有 future_ret，不会污染统计量）
        logger.info("\n截面预处理...")
        panel = self.preprocessor.preprocess_cross_section(panel, feature_cols)
        logger.info("预处理完成")

        # Step 4: 预处理完成后，再单独计算标签（不参与标准化）
        logger.info("计算标签（未来收益率）...")
        panel = panel.sort_values(['stock_code', 'trade_date'])
        panel['future_ret'] = panel.groupby('stock_code')['close'].transform(
            lambda x: x.shift(-self.config.predict_horizon) / x - 1
        )
        # 最后 predict_horizon 天没有 future_ret，是 NaN，属正常

        # 统计信息
        valid_labels = panel.dropna(subset=['future_ret'])
        dates = sorted(panel['trade_date'].unique())
        daily_counts = panel.groupby('trade_date')['stock_code'].nunique()

        logger.info(f"\n面板大小: {len(panel):,} 行 x {len(feature_cols)} 个因子")
        logger.info(f"交易日数: {len(dates)} ({dates[0].strftime('%Y-%m-%d')} ~ {dates[-1].strftime('%Y-%m-%d')})")
        logger.info(f"平均每日股票: {daily_counts.mean():.0f} 只")
        logger.info(f"未来{self.config.predict_horizon}日收益率: 均值={valid_labels['future_ret'].mean()*100:.3f}%, "
                   f"标准差={valid_labels['future_ret'].std()*100:.2f}%")

        return panel, feature_cols
