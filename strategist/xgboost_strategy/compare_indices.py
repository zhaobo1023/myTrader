# -*- coding: utf-8 -*-
"""
分别对上证50、沪深300、中证500、中证1000、中证2000 成分股运行 XGBoost 截面预测策略

运行: python -m strategist.xgboost_strategy.compare_indices
"""
import sys
import os
import logging
import warnings
import numpy as np
import pandas as pd
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, ROOT)

warnings.filterwarnings('ignore')

from strategist.xgboost_strategy.config import StrategyConfig
from strategist.xgboost_strategy.data_loader import DataLoader
from strategist.xgboost_strategy.backtest import XGBoostBacktest
from strategist.xgboost_strategy.feature_engine import get_all_feature_cols
from strategist.xgboost_strategy.model_trainer import ModelTrainer

logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_index_constituents():
    """从 AKShare 获取三大指数成分股"""
    import akshare as ak

    indices = {
        '上证50': '000016',
        '沪深300': '000300',
        '中证500': '000905',
        '中证1000': '000852',
        '中证2000': '932000',
    }

    result = {}
    for name, code in indices.items():
        df = ak.index_stock_cons(symbol=code)
        codes = df['品种代码'].tolist()
        formatted = []
        for c in codes:
            c = str(c).zfill(6)
            if c.startswith('6') or c.startswith('688'):
                formatted.append(f'{c}.SH')
            else:
                formatted.append(f'{c}.SZ')
        # 去重
        result[name] = list(dict.fromkeys(formatted))

    return result


def run_single_index(index_name, stock_pool, start_date='2023-01-01', end_date='2026-03-26'):
    """
    对单个指数成分股运行策略

    返回:
        dict with metrics, top_predictions, etc.
    """
    config = StrategyConfig()
    config.stock_pool = stock_pool
    config.start_date = start_date
    config.end_date = end_date
    config.train_window = 120
    config.predict_horizon = 5
    config.roll_step = 5

    # 1. 加载数据（保留无 future_ret 的行）
    data_loader = DataLoader(config)
    all_frames = []
    loaded = 0

    for code in stock_pool:
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
        except Exception:
            pass

    if loaded < 10:
        return None

    panel_all = pd.concat(all_frames, ignore_index=True)
    feature_cols = get_all_feature_cols()
    feature_cols = [c for c in feature_cols if c in panel_all.columns]
    panel_all = data_loader.preprocessor.preprocess_cross_section(panel_all, feature_cols)

    # 分离回测和预测数据
    panel_backtest = panel_all.dropna(subset=['future_ret']).copy()
    dates_all = sorted(panel_all['trade_date'].unique())

    # 2. 回测
    backtest = XGBoostBacktest(config)
    result = backtest.run_backtest(panel_backtest, feature_cols)
    if not result:
        return None

    metrics = result['metrics']

    # 3. 基于最新日期预测
    trainer = ModelTrainer(config)
    last_trainable_idx = len(dates_all) - config.predict_horizon
    if last_trainable_idx < config.train_window:
        return None

    train_start_idx = last_trainable_idx - config.train_window + 1
    train_dates = dates_all[train_start_idx:last_trainable_idx + 1]

    train_data = panel_all[
        (panel_all['trade_date'].isin(train_dates)) &
        (panel_all['future_ret'].notna())
    ]
    predict_date = dates_all[-1]
    test_data = panel_all[panel_all['trade_date'] == predict_date]

    X_train = train_data[feature_cols].fillna(0).values
    y_train = train_data['future_ret'].fillna(0).values
    X_test = test_data[feature_cols].fillna(0).values

    model = trainer.create_model()
    model.fit(X_train, y_train)
    predictions = model.predict(X_test)

    pred_df = pd.DataFrame({
        'stock_code': test_data['stock_code'].values,
        'prediction': predictions,
    }).sort_values('prediction', ascending=False).reset_index(drop=True)
    pred_df['rank'] = range(1, len(pred_df) + 1)

    # 组合收益统计
    portfolio_returns = result['portfolio_returns']
    portfolio_stats = {}
    if not portfolio_returns.empty:
        total_ret = portfolio_returns['cum_portfolio'].iloc[-1] - 1
        benchmark_ret = portfolio_returns['cum_benchmark'].iloc[-1] - 1
        excess_ret = total_ret - benchmark_ret
        # 计算最大回撤
        cum = portfolio_returns['cum_portfolio']
        rolling_max = cum.cummax()
        drawdown = (cum - rolling_max) / rolling_max
        max_drawdown = drawdown.min()
        # 年化收益
        n_days = len(portfolio_returns)
        ann_ret = (1 + total_ret) ** (252 / n_days) - 1
        # 夏普比率 (假设无风险利率2%)
        daily_excess = portfolio_returns['portfolio_return'] - 0.02 / 252
        sharpe = daily_excess.mean() / daily_excess.std() * np.sqrt(252) if daily_excess.std() > 0 else 0

        portfolio_stats = {
            'total_return': total_ret,
            'benchmark_return': benchmark_ret,
            'excess_return': excess_ret,
            'max_drawdown': max_drawdown,
            'annual_return': ann_ret,
            'sharpe': sharpe,
            'n_trading_days': n_days,
        }

    return {
        'index_name': index_name,
        'n_stocks': loaded,
        'metrics': metrics,
        'portfolio_stats': portfolio_stats,
        'latest_prediction': pred_df,
        'predict_date': predict_date,
        'feature_importance': pd.DataFrame({
            'feature': feature_cols,
            'importance': model.feature_importances_,
        }).sort_values('importance', ascending=False),
    }


def main():
    print("\n" + "=" * 80)
    print("XGBoost 截面预测 - 上证50 / 沪深300 / 中证500 对比")
    print("=" * 80)

    # 获取成分股
    print("\n获取指数成分股...")
    constituents = get_index_constituents()
    for name, codes in constituents.items():
        print(f"  {name}: {len(codes)} 只")

    # 分别运行
    results = {}
    for index_name, stock_pool in constituents.items():
        print(f"\n{'=' * 80}")
        print(f">>> 正在运行: {index_name} ({len(stock_pool)} 只)")
        print(f"{'=' * 80}")

        result = run_single_index(index_name, stock_pool)
        if result:
            results[index_name] = result
            m = result['metrics']
            ps = result['portfolio_stats']
            print(f"\n  IC:        {m['IC']:.4f}")
            print(f"  ICIR:      {m['ICIR']:.4f}")
            print(f"  RankIC:    {m['RankIC']:.4f}")
            print(f"  RankICIR:  {m['RankICIR']:.4f}")
            print(f"  IC>0占比:  {m['IC_positive_rate']:.1%}")
            if ps:
                print(f"  策略总收益: {ps['total_return']*100:+.2f}%")
                print(f"  基准总收益: {ps['benchmark_return']*100:+.2f}%")
                print(f"  超额收益:   {ps['excess_return']*100:+.2f}%")
                print(f"  最大回撤:   {ps['max_drawdown']*100:.2f}%")
                print(f"  年化收益:   {ps['annual_return']*100:+.2f}%")
                print(f"  夏普比率:   {ps['sharpe']:.3f}")
        else:
            print(f"  运行失败!")

    # 对比汇总
    names = ['上证50', '沪深300', '中证500', '中证1000', '中证2000']
    valid_names = [n for n in names if n in results]
    r = [results[n] for n in valid_names]
    col_w = 12

    print("\n\n" + "=" * (16 + col_w * len(valid_names) + len(valid_names) * 3))
    print("对比汇总")
    print("=" * (16 + col_w * len(valid_names) + len(valid_names) * 3))

    header = f"{'指标':<16}" + "".join(f"{n:>{col_w}}" for n in valid_names)
    print(header)
    print("-" * (16 + col_w * len(valid_names) + len(valid_names) * 3))

    # IC 指标
    ic_data = [
        ('股票数量', [f"{x['n_stocks']}只" for x in r]),
        ('IC', [f"{x['metrics']['IC']:.4f}" for x in r]),
        ('ICIR', [f"{x['metrics']['ICIR']:.4f}" for x in r]),
        ('RankIC', [f"{x['metrics']['RankIC']:.4f}" for x in r]),
        ('RankICIR', [f"{x['metrics']['RankICIR']:.4f}" for x in r]),
        ('IC>0占比', [f"{x['metrics']['IC_positive_rate']:.1%}" for x in r]),
    ]

    for label, values in ic_data:
        row = f"{label:<16}" + "".join(f"{v:>{col_w}}" for v in values)
        print(row)

    print()

    # 收益指标
    ret_data = [
        ('策略总收益', [f"{x['portfolio_stats']['total_return']*100:+.2f}%" for x in r]),
        ('基准总收益', [f"{x['portfolio_stats']['benchmark_return']*100:+.2f}%" for x in r]),
        ('超额收益', [f"{x['portfolio_stats']['excess_return']*100:+.2f}%" for x in r]),
        ('最大回撤', [f"{x['portfolio_stats']['max_drawdown']*100:.2f}%" for x in r]),
        ('年化收益', [f"{x['portfolio_stats']['annual_return']*100:+.2f}%" for x in r]),
        ('夏普比率', [f"{x['portfolio_stats']['sharpe']:.3f}" for x in r]),
    ]

    for label, values in ret_data:
        row = f"{label:<16}" + "".join(f"{v:>{col_w}}" for v in values)
        print(row)

    # 各指数 Top 10 预测
    print("\n")
    for index_name, result in results.items():
        pred_df = result['latest_prediction']
        pred_date = result['predict_date']
        print(f"{'=' * 60}")
        print(f"{index_name} - 基于 {pred_date.strftime('%Y-%m-%d')} 预测未来5日 Top 10")
        print(f"{'=' * 60}")
        print(f"{'排名':>4}  {'股票代码':<12} {'预测收益率':>10}")
        print("-" * 35)
        for _, row in pred_df.head(10).iterrows():
            print(f"{row['rank']:>4}  {row['stock_code']:<12} {row['prediction']:>+10.4f}")
        print()

    # 保存结果
    output_dir = os.path.join(ROOT, 'output', 'xgboost')
    os.makedirs(output_dir, exist_ok=True)

    for index_name, result in results.items():
        safe_name = index_name.replace('/', '_')
        # 保存预测信号
        pred_file = os.path.join(output_dir, f'{safe_name}_prediction.csv')
        result['latest_prediction'].to_csv(pred_file, index=False, encoding='utf-8-sig')
        # 保存特征重要性
        imp_file = os.path.join(output_dir, f'{safe_name}_feature_importance.csv')
        result['feature_importance'].to_csv(imp_file, index=False, encoding='utf-8-sig')

    # 保存对比汇总
    summary_rows = []
    for index_name, result in results.items():
        m = result['metrics']
        ps = result['portfolio_stats']
        summary_rows.append({
            '指数': index_name,
            '股票数': result['n_stocks'],
            'IC': m['IC'],
            'ICIR': m['ICIR'],
            'RankIC': m['RankIC'],
            'RankICIR': m['RankICIR'],
            'IC>0占比': m['IC_positive_rate'],
            '策略总收益': ps.get('total_return', 0),
            '超额收益': ps.get('excess_return', 0),
            '最大回撤': ps.get('max_drawdown', 0),
            '年化收益': ps.get('annual_return', 0),
            '夏普比率': ps.get('sharpe', 0),
        })
    summary_df = pd.DataFrame(summary_rows)
    summary_file = os.path.join(output_dir, 'index_comparison.csv')
    summary_df.to_csv(summary_file, index=False, encoding='utf-8-sig')

    print(f"\n结果已保存到: {output_dir}")
    print("  - index_comparison.csv (对比汇总)")
    for index_name in results:
        safe_name = index_name.replace('/', '_')
        print(f"  - {safe_name}_prediction.csv ({index_name} 预测信号)")
        print(f"  - {safe_name}_feature_importance.csv ({index_name} 特征重要性)")

    print("\n" + "=" * 80)
    print("全部完成!")
    print("=" * 80)


if __name__ == "__main__":
    main()
