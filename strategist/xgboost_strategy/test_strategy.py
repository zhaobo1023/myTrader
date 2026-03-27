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
