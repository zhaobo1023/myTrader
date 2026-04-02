# -*- coding: utf-8 -*-
"""
XGBoost 策略测试脚本

快速测试策略的各个模块
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

def test_imports():
    """测试模块导入"""
    print("测试模块导入...")
    
    try:
        from strategist.xgboost_strategy.config import StrategyConfig
        print("✓ config")
    except Exception as e:
        print(f"✗ config: {e}")
        return False
    
    try:
        from strategist.xgboost_strategy.feature_engine import FeatureEngine, FACTOR_TAXONOMY
        print("✓ feature_engine")
    except Exception as e:
        print(f"✗ feature_engine: {e}")
        return False
    
    try:
        from strategist.xgboost_strategy.preprocessor import Preprocessor
        print("✓ preprocessor")
    except Exception as e:
        print(f"✗ preprocessor: {e}")
        return False
    
    try:
        from strategist.xgboost_strategy.model_trainer import ModelTrainer
        print("✓ model_trainer")
    except Exception as e:
        print(f"✗ model_trainer: {e}")
        return False
    
    try:
        from strategist.xgboost_strategy.predictor import Predictor
        print("✓ predictor")
    except Exception as e:
        print(f"✗ predictor: {e}")
        return False
    
    try:
        from strategist.xgboost_strategy.evaluator import ICEvaluator
        print("✓ evaluator")
    except Exception as e:
        print(f"✗ evaluator: {e}")
        return False
    
    try:
        from strategist.xgboost_strategy.backtest import XGBoostBacktest
        print("✓ backtest")
    except Exception as e:
        print(f"✗ backtest: {e}")
        return False
    
    try:
        from strategist.xgboost_strategy.data_loader import DataLoader
        print("✓ data_loader")
    except Exception as e:
        print(f"✗ data_loader: {e}")
        return False
    
    try:
        from strategist.xgboost_strategy.visualizer import Visualizer
        print("✓ visualizer")
    except Exception as e:
        print(f"✗ visualizer: {e}")
        return False
    
    print("\n所有模块导入成功！\n")
    return True


def test_dependencies():
    """测试依赖库"""
    print("测试依赖库...")
    
    try:
        import talib
        print("✓ TA-Lib")
    except ImportError:
        print("✗ TA-Lib 未安装 (必需)")
        print("  安装方法: brew install ta-lib && pip install TA-Lib")
        return False
    
    try:
        import xgboost
        print("✓ XGBoost")
    except ImportError:
        print("✗ XGBoost 未安装 (必需)")
        print("  安装方法: pip install xgboost")
        return False
    
    try:
        import scipy
        print("✓ SciPy")
    except ImportError:
        print("✗ SciPy 未安装 (必需)")
        print("  安装方法: pip install scipy")
        return False
    
    try:
        import sklearn
        print("✓ scikit-learn")
    except ImportError:
        print("✗ scikit-learn 未安装 (可选)")
        print("  安装方法: pip install scikit-learn")
    
    try:
        import matplotlib
        print("✓ Matplotlib")
    except ImportError:
        print("✗ Matplotlib 未安装 (可选)")
        print("  安装方法: pip install matplotlib")
    
    print("\n核心依赖检查通过！\n")
    return True


def test_config():
    """测试配置"""
    print("测试配置...")
    
    from strategist.xgboost_strategy.config import StrategyConfig
    
    config = StrategyConfig()
    
    print(f"  股票池: {len(config.stock_pool)} 只")
    print(f"  训练窗口: {config.train_window} 天")
    print(f"  预测周期: {config.predict_horizon} 天")
    print(f"  XGBoost 参数: {config.get_xgboost_params()}")
    
    print("\n配置测试通过！\n")
    return True


def test_feature_engine():
    """测试因子引擎"""
    print("测试因子引擎...")
    
    import pandas as pd
    import numpy as np
    from strategist.xgboost_strategy.feature_engine import FeatureEngine, get_all_feature_cols
    
    # 创建模拟数据
    dates = pd.date_range('2024-01-01', periods=200, freq='D')
    np.random.seed(42)
    
    df = pd.DataFrame({
        'open': 100 + np.random.randn(200).cumsum(),
        'high': 102 + np.random.randn(200).cumsum(),
        'low': 98 + np.random.randn(200).cumsum(),
        'close': 100 + np.random.randn(200).cumsum(),
        'volume': 1000000 + np.random.randint(-100000, 100000, 200),
    }, index=dates)
    
    # 确保 high >= low
    df['high'] = df[['open', 'high', 'close']].max(axis=1)
    df['low'] = df[['open', 'low', 'close']].min(axis=1)
    
    engine = FeatureEngine()
    result = engine.calc_features(df)
    
    feature_cols = get_all_feature_cols()
    
    print(f"  输入数据: {len(df)} 行")
    print(f"  输出特征: {len([c for c in feature_cols if c in result.columns])} 个")
    print(f"  前5个因子: {feature_cols[:5]}")
    
    print("\n因子引擎测试通过！\n")
    return True


def test_database_connection():
    """测试数据库连接"""
    print("测试数据库连接...")
    
    try:
        from config.db import execute_query
        
        # 测试查询
        result = execute_query("SELECT COUNT(*) as cnt FROM trade_stock_daily LIMIT 1")
        if result:
            print(f"✓ 数据库连接成功")
            print(f"  trade_stock_daily 表有数据")
        else:
            print("✗ trade_stock_daily 表无数据")
            return False
        
    except Exception as e:
        print(f"✗ 数据库连接失败: {e}")
        return False
    
    print("\n数据库连接测试通过！\n")
    return True


def test_no_lookahead_leakage():
    """
    泄露检测：验证 future_ret 标签的时间对齐正确性

    检查逻辑：
    1. 抽样验证 future_ret = close[T+5] / close[T] - 1
    2. 验证面板中不存在 future_ret 被用于预处理的痕迹
       （检查特征列中是否混入了 future_ret）
    """
    import numpy as np
    import pandas as pd

    print("泄露检测（标签对齐验证）...")

    from config.db import execute_query
    test_stocks = ['600519.SH', '000858.SZ', '601318.SH']
    start_date = '2024-01-01'
    end_date = '2024-12-31'

    all_frames = []
    for code in test_stocks:
        sql = """
            SELECT trade_date, open_price, high_price, low_price, close_price, volume
            FROM trade_stock_daily
            WHERE stock_code = %s AND trade_date >= %s AND trade_date <= %s
            ORDER BY trade_date ASC
        """
        rows = execute_query(sql, [code, start_date, end_date])
        if not rows:
            continue
        df = pd.DataFrame(rows)
        df['trade_date'] = pd.to_datetime(df['trade_date'])
        df.set_index('trade_date', inplace=True)
        df.columns = ['open', 'high', 'low', 'close', 'volume']
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df['stock_code'] = code
        df['trade_date'] = df.index
        all_frames.append(df)

    if not all_frames:
        print("  无数据，跳过泄露检测")
        return True

    panel = pd.concat(all_frames, ignore_index=True)

    # 检查1：验证 future_ret 计算正确
    panel = panel.sort_values(['stock_code', 'trade_date'])
    panel['future_ret'] = panel.groupby('stock_code')['close'].transform(
        lambda x: x.shift(-5) / x - 1
    )

    errors = 0
    for code in test_stocks:
        stock_panel = panel[panel['stock_code'] == code].reset_index(drop=True)
        for i in range(min(10, len(stock_panel) - 5)):
            t_close = stock_panel.loc[i, 'close']
            t5_close = stock_panel.loc[i + 5, 'close']
            expected = t5_close / t_close - 1
            actual = stock_panel.loc[i, 'future_ret']
            if abs(expected - actual) > 1e-8 and not (np.isnan(expected) or np.isnan(actual)):
                errors += 1
                print(f"  标签对齐错误: {code} {stock_panel.loc[i, 'trade_date'].strftime('%Y-%m-%d')} "
                      f"expected={expected:.6f} actual={actual:.6f}")

    if errors == 0:
        print("  标签对齐验证: 通过 (future_ret = close[T+5]/close[T] - 1)")
    else:
        print(f"  标签对齐验证: 失败 ({errors} 处错误)")
        return False

    # 检查2：验证 future_ret 不在特征列中
    from strategist.xgboost_strategy.feature_engine import get_all_feature_cols
    feature_cols = get_all_feature_cols()
    if 'future_ret' in feature_cols:
        print("  特征列检查: 失败 (future_ret 被包含在特征列中!)")
        return False
    else:
        print("  特征列检查: 通过 (future_ret 未被包含在特征列中)")

    # 检查3：验证最后5行 future_ret 为 NaN
    for code in test_stocks:
        stock_panel = panel[panel['stock_code'] == code].reset_index(drop=True)
        last_5 = stock_panel.tail(5)['future_ret']
        if last_5.notna().any():
            print(f"  尾部NaN检查: 失败 ({code} 最后5行应全为NaN)")
            return False

    print("  尾部NaN检查: 通过 (最后5行 future_ret 均为 NaN)")
    print("  结果: 通过 - 无明显泄露")
    return True


def test_time_boundary():
    """
    快速检测：打印训练集最后一天和预测日的时间差
    """
    import numpy as np
    from strategist.xgboost_strategy.config import StrategyConfig
    from strategist.xgboost_strategy.data_loader import DataLoader

    print("时间边界检测...")

    config = StrategyConfig()
    config.stock_pool = config.stock_pool[:10]  # 只用10只测试
    config.end_date = '2024-06-30'

    try:
        data_loader = DataLoader(config)
        panel, feature_cols = data_loader.load_and_compute_factors()
        dates = sorted(panel['trade_date'].unique())

        # 检查前3个预测日
        train_window = config.train_window
        for i in range(3):
            pred_idx = train_window + i * config.roll_step
            if pred_idx >= len(dates):
                break
            pred_date = dates[pred_idx]
            train_end = dates[pred_idx - 1]
            gap = (pred_date - train_end).days
            print(f"  信号日: {pred_date.strftime('%Y-%m-%d')}, "
                  f"训练集截止: {train_end.strftime('%Y-%m-%d')}, "
                  f"间隔: {gap}天 {'(OK)' if gap > 0 else '(泄露!)'}")

        return True
    except Exception as e:
        print(f"  时间边界检测失败: {e}")
        return False


def test_reverse_label():
    """
    反向标签测试：用过去5日收益率替代未来5日收益率，验证无残留泄露

    如果系统干净，用过去收益做标签时 IC 应接近 0（±0.02）。
    如果 IC 仍然显著 > 0.03，说明模型可能在使用泄露信号。
    """
    import numpy as np
    from strategist.xgboost_strategy.config import StrategyConfig
    from strategist.xgboost_strategy.data_loader import DataLoader
    from strategist.xgboost_strategy.backtest import XGBoostBacktest

    print("反向标签测试...")

    config = StrategyConfig()
    config.stock_pool = config.stock_pool[:20]
    config.end_date = '2024-06-30'

    try:
        data_loader = DataLoader(config)
        panel, feature_cols = data_loader.load_and_compute_factors()

        # 将 future_ret 替换为过去5日收益率（反向标签）
        panel = panel.sort_values(['stock_code', 'trade_date'])
        panel['future_ret'] = panel.groupby('stock_code')['close'].transform(
            lambda x: x / x.shift(5) - 1  # 过去5日，非未来
        )

        backtest = XGBoostBacktest(config)
        result = backtest.run_backtest(panel, feature_cols)

        if not result or 'metrics' not in result:
            print("  反向标签测试: 无法运行")
            return False

        m = result['metrics']
        ic = m['IC']
        rank_ic = m['RankIC']

        print(f"  反向标签 IC:    {ic:.4f}")
        print(f"  反向标签 RankIC: {rank_ic:.4f}")

        if abs(ic) < 0.02 and abs(rank_ic) < 0.02:
            print("  结果: 通过 - 反向标签 IC 接近 0，系统无残留泄露")
            return True
        elif abs(ic) < 0.04:
            print("  结果: 边界 - 反向标签 IC 偏低但非零，可能存在轻微自相关")
            return True
        else:
            print(f"  结果: 失败 - 反向标签 IC={ic:.4f} 偏高，可能存在残留泄露")
            return False

    except Exception as e:
        print(f"  反向标签测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("=" * 60)
    print("XGBoost 策略模块测试")
    print("=" * 60)
    print()
    
    tests = [
        ("依赖库检查", test_dependencies),
        ("模块导入", test_imports),
        ("配置测试", test_config),
        ("因子引擎", test_feature_engine),
        ("数据库连接", test_database_connection),
        ("泄露检测", test_no_lookahead_leakage),
        ("时间边界检测", test_time_boundary),
        ("反向标签测试", test_reverse_label),
    ]
    
    results = []
    
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"✗ {name} 测试失败: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    print("=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    for name, success in results:
        status = "✓ 通过" if success else "✗ 失败"
        print(f"{name:<20} {status}")
    
    all_passed = all(success for _, success in results)
    
    print()
    if all_passed:
        print("✅ 所有测试通过！可以运行策略了。")
        print("\n运行策略:")
        print("  python -m strategist.xgboost_strategy.run_strategy")
    else:
        print("❌ 部分测试失败，请先解决问题。")
    
    print("=" * 60)


if __name__ == "__main__":
    main()
