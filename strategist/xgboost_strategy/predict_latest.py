# -*- coding: utf-8 -*-
"""
基于最新数据（到 2026-03-26）的截面预测

功能：
1. 加载全量数据到 2026-03-26，计算因子
2. 正常回测（有 future_ret 的部分）
3. 用最后一个训练窗口训练模型，预测 2026-03-26 截面的未来5日收益率排名
4. 输出 Top N 推荐股票

运行: python -m strategist.xgboost_strategy.predict_latest
"""
import sys
import os
import logging
import numpy as np
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from strategist.xgboost_strategy.config import StrategyConfig
from strategist.xgboost_strategy.data_loader import DataLoader
from strategist.xgboost_strategy.backtest import XGBoostBacktest
from strategist.xgboost_strategy.visualizer import Visualizer
from strategist.xgboost_strategy.feature_engine import get_all_feature_cols, FACTOR_TAXONOMY
from strategist.xgboost_strategy.model_trainer import ModelTrainer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    print("\n" + "=" * 80)
    print("XGBoost 截面预测 - 基于最新数据")
    print("=" * 80)

    # 配置：end_date 到 2026-03-26
    config = StrategyConfig()
    config.end_date = '2026-03-26'
    config.start_date = '2023-01-01'

    print(f"股票池: {len(config.stock_pool)} 只")
    print(f"数据范围: {config.start_date} ~ {config.end_date}")
    print(f"训练窗口: {config.train_window} 交易日")
    print(f"预测目标: 未来 {config.predict_horizon} 日收益率")

    # 1. 加载数据并计算因子（保留未来收益为NaN的行）
    logger.info("\n[1/4] 加载数据并计算因子...")
    data_loader = DataLoader(config)

    stock_pool = config.stock_pool
    start_date = config.start_date
    end_date = config.end_date

    all_frames = []
    loaded = 0
    for i, code in enumerate(stock_pool, 1):
        try:
            df = data_loader.load_stock_data(code, start_date, end_date)
            if len(df) < config.min_bars:
                continue
            feat_df = data_loader.feature_engine.calc_features(df)
            feat_df['future_ret'] = feat_df['close'].pct_change(config.predict_horizon).shift(-config.predict_horizon)
            feat_df['stock_code'] = code
            feat_df['trade_date'] = feat_df.index
            all_frames.append(feat_df)
            loaded += 1
        except Exception as e:
            logger.error(f"{code}: {e}")

    panel_all = pd.concat(all_frames, ignore_index=True)
    feature_cols = get_all_feature_cols()
    feature_cols = [c for c in feature_cols if c in panel_all.columns]

    # 截面预处理（包含所有日期）
    panel_all = data_loader.preprocessor.preprocess_cross_section(panel_all, feature_cols)

    # 分离：有 future_ret 的用于回测，没有的用于预测
    panel_backtest = panel_all.dropna(subset=['future_ret']).copy()
    panel_predict = panel_all[panel_all['future_ret'].isna()].copy()

    dates_all = sorted(panel_all['trade_date'].unique())
    dates_backtest = sorted(panel_backtest['trade_date'].unique())
    dates_predict = sorted(panel_predict['trade_date'].unique())

    logger.info(f"总交易日: {len(dates_all)} ({dates_all[0].strftime('%Y-%m-%d')} ~ {dates_all[-1].strftime('%Y-%m-%d')})")
    logger.info(f"回测区间: {len(dates_backtest)} 天 ({dates_backtest[0].strftime('%Y-%m-%d')} ~ {dates_backtest[-1].strftime('%Y-%m-%d')})")
    logger.info(f"待预测日期: {dates_predict}")

    # 2. 正常回测
    logger.info("\n[2/4] 运行回测...")
    backtest = XGBoostBacktest(config)
    result = backtest.run_backtest(panel_backtest, feature_cols)

    if not result:
        logger.error("回测失败")
        return

    # 3. 单因子 IC 分析
    logger.info("\n单因子 IC 分析...")
    factor_ic_df = backtest.analyze_factor_ic(panel_backtest, feature_cols)

    if not factor_ic_df.empty:
        print("\n" + "=" * 60)
        print("因子 IC 排名 (Top 10, 按 |ICIR| 排序)")
        print("=" * 60)
        print(f"{'因子':<28} {'IC':>8} {'ICIR':>8} {'RankIC':>8} {'RICIR':>8} {'IC>0':>6}")
        print("-" * 75)
        for _, row in factor_ic_df.head(10).iterrows():
            print(f"{row['factor']:<28} {row['IC']:>8.4f} {row['ICIR']:>8.4f} "
                  f"{row['RankIC']:>8.4f} {row['RankICIR']:>8.4f} {row['IC_positive']:>5.1%}")

    # 4. 基于最新数据预测未来5日收益
    logger.info("\n[3/4] 基于最新截面预测未来5日收益率...")
    trainer = ModelTrainer(config)

    # 使用最后一个可用的训练窗口
    # 找到 panel_all 中最后一个有 future_ret 的日期，向前推 train_window 天作为训练集
    last_trainable_idx = len(dates_all) - config.predict_horizon  # 最后一个有 future_ret 的日期的索引
    last_trainable_date = dates_all[last_trainable_idx]

    # 训练窗口：从 last_trainable_idx - train_window + 1 到 last_trainable_idx
    train_start_idx = last_trainable_idx - config.train_window + 1
    if train_start_idx < 0:
        train_start_idx = 0
    train_dates = dates_all[train_start_idx:last_trainable_idx + 1]

    # 训练数据：只使用有 future_ret 的行
    train_data = panel_all[
        (panel_all['trade_date'].isin(train_dates)) &
        (panel_all['future_ret'].notna())
    ]

    # 预测数据：最后一个交易日
    predict_date = dates_all[-1]
    test_data = panel_all[panel_all['trade_date'] == predict_date]

    logger.info(f"训练窗口: {train_dates[0].strftime('%Y-%m-%d')} ~ {train_dates[-1].strftime('%Y-%m-%d')} ({len(train_dates)} 天)")
    logger.info(f"训练样本: {len(train_data)} 行")
    logger.info(f"预测日期: {predict_date.strftime('%Y-%m-%d')}")
    logger.info(f"预测股票: {len(test_data)} 只")

    X_train = train_data[feature_cols].fillna(0).values
    y_train = train_data['future_ret'].fillna(0).values
    X_test = test_data[feature_cols].fillna(0).values

    # 训练模型
    model = trainer.create_model()
    model.fit(X_train, y_train)

    # 预测
    predictions = model.predict(X_test)
    stock_codes = test_data['stock_code'].values

    # 构建预测结果 DataFrame
    pred_df = pd.DataFrame({
        'stock_code': stock_codes,
        'prediction': predictions,
    })
    pred_df = pred_df.sort_values('prediction', ascending=False).reset_index(drop=True)
    pred_df['rank'] = range(1, len(pred_df) + 1)

    # 输出 Top N 推荐
    top_n = config.top_n
    print("\n" + "=" * 80)
    print(f"基于 {predict_date.strftime('%Y-%m-%d')} 数据，预测未来5日收益率 Top {top_n}")
    print("=" * 80)
    print(f"{'排名':>4}  {'股票代码':<12} {'预测收益率':>10}")
    print("-" * 35)
    for _, row in pred_df.head(top_n).iterrows():
        print(f"{row['rank']:>4}  {row['stock_code']:<12} {row['prediction']:>+10.4f}")

    print(f"\n{'排名':>4}  {'股票代码':<12} {'预测收益率':>10}")
    print("-" * 35)
    print("(Bottom 5 看空)")
    for _, row in pred_df.tail(5).iterrows():
        print(f"{row['rank']:>4}  {row['stock_code']:<12} {row['prediction']:>+10.4f}")

    # 特征重要性
    importance_df = pd.DataFrame({
        'feature': feature_cols,
        'importance': model.feature_importances_,
    }).sort_values('importance', ascending=False)

    print("\n" + "=" * 60)
    print("特征重要性 Top 10")
    print("=" * 60)
    for _, row in importance_df.head(10).iterrows():
        print(f"  {row['feature']:<28} {row['importance']:.4f}")

    # 5. 保存结果
    logger.info("\n[4/4] 保存结果...")
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
    os.makedirs(output_dir, exist_ok=True)

    # 保存预测信号
    pred_file = os.path.join(output_dir, 'latest_prediction.csv')
    pred_df.to_csv(pred_file, index=False, encoding='utf-8-sig')
    logger.info(f"最新预测信号: {pred_file}")

    # 保存回测结果
    signals_file = os.path.join(output_dir, 'signals.csv')
    result['signals'].to_csv(signals_file, index=False, encoding='utf-8-sig')

    if not result['portfolio_returns'].empty:
        returns_file = os.path.join(output_dir, 'portfolio_returns.csv')
        result['portfolio_returns'].to_csv(returns_file, index=False, encoding='utf-8-sig')

    if not factor_ic_df.empty:
        factor_ic_file = os.path.join(output_dir, 'factor_ic.csv')
        factor_ic_df.to_csv(factor_ic_file, index=False, encoding='utf-8-sig')

    # 可视化
    visualizer = Visualizer(output_dir)
    visualizer.plot_ic_analysis(result['metrics'])
    if not result['portfolio_returns'].empty:
        visualizer.plot_portfolio_performance(result['portfolio_returns'])
    if not factor_ic_df.empty:
        visualizer.plot_factor_ic(factor_ic_df)

    # 保存完整预测（含所有股票）
    full_pred_file = os.path.join(output_dir, 'full_prediction.csv')
    pred_df.to_csv(full_pred_file, index=False, encoding='utf-8-sig')

    # 保存特征重要性
    imp_file = os.path.join(output_dir, 'feature_importance.csv')
    importance_df.to_csv(imp_file, index=False, encoding='utf-8-sig')

    print("\n" + "=" * 80)
    print("运行完成!")
    print(f"输出目录: {output_dir}")
    print(f"最新预测: latest_prediction.csv (Top {top_n} 推荐)")
    print(f"全部排名: full_prediction.csv ({len(pred_df)} 只股票)")
    print("=" * 80)


if __name__ == "__main__":
    main()
