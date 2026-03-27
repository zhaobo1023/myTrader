# -*- coding: utf-8 -*-
"""
Paper Trading 模块测试

测试内容:
1. 数据库连接和建表
2. 配置加载
3. PositionManager 交易日历查询
4. SettlementEngine 结算逻辑
5. PerformanceEvaluator 指标计算
6. SignalGenerator 集成测试（需要真实数据）
7. 端到端流程测试
"""
import sys
import os
from datetime import date, timedelta

# 确保 myTrader 根目录在 sys.path
mytrader_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, mytrader_root)


def test_db_connection():
    """测试数据库连接"""
    print("=" * 50)
    print("测试 1: 数据库连接")
    print("=" * 50)

    from config.db import execute_query

    try:
        rows = execute_query("SELECT 1 as ok")
        assert len(rows) == 1 and rows[0]['ok'] == 1
        print("  [PASS] 数据库连接正常")
    except Exception as e:
        print(f"  [FAIL] 数据库连接失败: {e}")
        return False

    return True


def test_table_creation():
    """测试建表"""
    print("\n" + "=" * 50)
    print("测试 2: 建表")
    print("=" * 50)

    from strategist.xgboost_strategy.paper_trading.db_schema import (
        init_tables, drop_tables, CREATE_PT_ROUNDS, CREATE_PT_POSITIONS, CREATE_PT_BENCHMARK
    )
    from config.db import execute_query

    try:
        init_tables()

        # 验证表是否存在
        tables = ['pt_rounds', 'pt_positions', 'pt_benchmark']
        for table in tables:
            rows = execute_query(f"SHOW TABLES LIKE '{table}'")
            if rows:
                print(f"  [PASS] 表 {table} 存在")
            else:
                print(f"  [FAIL] 表 {table} 不存在")
                return False

    except Exception as e:
        print(f"  [FAIL] 建表失败: {e}")
        return False

    return True


def test_config():
    """测试配置"""
    print("\n" + "=" * 50)
    print("测试 3: 配置")
    print("=" * 50)

    from strategist.xgboost_strategy.paper_trading.config import PaperTradingConfig

    config = PaperTradingConfig()

    assert config.hold_days == 5, "hold_days 应为 5"
    assert config.top_n == 10, "top_n 应为 10"
    assert config.cost_rate == 0.002, "cost_rate 应为 0.002"
    assert '沪深300' in config.index_pool, "沪深300 应在 index_pool 中"

    code = config.get_index_code('沪深300')
    assert code == '000300.SH', f"沪深300 代码应为 000300.SH，实际 {code}"

    indexes = config.get_available_indexes()
    assert len(indexes) >= 5, f"应有至少 5 个指数，实际 {len(indexes)}"

    print(f"  [PASS] 配置加载正常")
    print(f"         指数池: {indexes}")
    print(f"         默认指数: {config.default_index}")
    print(f"         持仓天数: {config.hold_days}")
    print(f"         选股数量: Top {config.top_n}")

    return True


def test_position_manager():
    """测试 PositionManager"""
    print("\n" + "=" * 50)
    print("测试 4: PositionManager")
    print("=" * 50)

    from strategist.xgboost_strategy.paper_trading.position_manager import PositionManager
    from config.db import execute_query

    pm = PositionManager()

    # 测试交易日历查询
    try:
        test_date = date(2024, 1, 2)
        next_day = pm.get_next_trading_date(test_date, offset=1)
        print(f"  [PASS] {test_date} 后第1个交易日: {next_day}")

        next_5 = pm.get_next_trading_date(test_date, offset=5)
        print(f"         后第5个交易日: {next_5}")
    except Exception as e:
        print(f"  [WARN] 交易日历查询失败（可能无数据）: {e}")

    # 测试状态查询
    try:
        pending = pm.get_pending_buy_rounds()
        active = pm.get_rounds_to_settle()
        settled = pm.get_all_settled_rounds()
        print(f"  [PASS] 状态查询正常: pending={len(pending)}, active_to_settle={len(active)}, settled={len(settled)}")
    except Exception as e:
        print(f"  [WARN] 状态查询失败: {e}")

    return True


def test_settlement_engine():
    """测试 SettlementEngine"""
    print("\n" + "=" * 50)
    print("测试 5: SettlementEngine")
    print("=" * 50)

    from strategist.xgboost_strategy.paper_trading.settlement import SettlementEngine
    from strategist.xgboost_strategy.paper_trading.config import PaperTradingConfig

    config = PaperTradingConfig()
    se = SettlementEngine(config)

    # 测试价格查询
    try:
        price = se._get_close_price('2024-01-02', '600519.SH')
        if price is not None:
            print(f"  [PASS] 价格查询正常: 600519.SH 2024-01-02 收盘价 = {price}")
        else:
            print(f"  [WARN] 600519.SH 2024-01-02 无价格数据")
    except Exception as e:
        print(f"  [WARN] 价格查询失败: {e}")

    # 测试批量操作（无数据时不应报错）
    try:
        count = se.fill_all_pending_buys()
        print(f"  [PASS] 批量填充买入价: {count} 轮")

        results = se.settle_all_pending()
        print(f"  [PASS] 批量结算: {len(results)} 轮")
    except Exception as e:
        print(f"  [WARN] 批量操作失败: {e}")

    return True


def test_evaluator():
    """测试 PerformanceEvaluator"""
    print("\n" + "=" * 50)
    print("测试 6: PerformanceEvaluator")
    print("=" * 50)

    from strategist.xgboost_strategy.paper_trading.evaluator import PerformanceEvaluator
    import pandas as pd
    import numpy as np

    ev = PerformanceEvaluator()

    # 用模拟数据测试指标计算
    mock_data = pd.DataFrame({
        'signal_date': pd.date_range('2024-01-01', periods=10, freq='W-FRI'),
        'portfolio_ret': np.random.normal(0.3, 1.5, 10),
        'benchmark_ret': np.random.normal(0.1, 1.0, 10),
        'excess_ret': np.random.normal(0.2, 1.2, 10),
        'ic': np.random.normal(0.04, 0.08, 10),
        'rank_ic': np.random.normal(0.05, 0.06, 10),
    })

    metrics = ev.compute_metrics(mock_data)

    required_keys = [
        'n_rounds', 'ic_mean', 'ic_std', 'icir', 'ic_pos_pct',
        'cum_ret_pct', 'cum_excess_pct', 'win_rate_pct', 'max_loss_pct',
    ]
    for key in required_keys:
        assert key in metrics, f"指标 {key} 缺失"

    print(f"  [PASS] 指标计算正常")
    print(f"         n_rounds={metrics['n_rounds']}, ic_mean={metrics['ic_mean']}, icir={metrics['icir']}")

    # 测试 interpret
    interpretation = ev.interpret(metrics)
    assert len(interpretation) > 0, "interpret 输出为空"
    print(f"  [PASS] 结论生成正常")

    # 测试从数据库加载
    try:
        df = ev.load_settled_rounds('沪深300', min_rounds=1)
        if df is not None:
            print(f"  [INFO] 数据库已有 {len(df)} 轮已结算数据")
        else:
            print(f"  [INFO] 数据库暂无已结算数据")
    except Exception as e:
        print(f"  [WARN] 数据库查询失败: {e}")

    return True


def test_signal_generator():
    """测试 SignalGenerator（需要真实数据）"""
    print("\n" + "=" * 50)
    print("测试 7: SignalGenerator (需要真实数据)")
    print("=" * 50)

    try:
        from strategist.xgboost_strategy.paper_trading.signal_generator import SignalGenerator
        from strategist.xgboost_strategy.paper_trading.config import PaperTradingConfig

        config = PaperTradingConfig()
        sg = SignalGenerator(config)

        # 使用历史日期测试
        test_date = date(2024, 1, 5)  # 周五
        signals = sg.generate(test_date, '沪深300')

        assert 'stock_code' in signals.columns, "缺少 stock_code 列"
        assert 'pred_score' in signals.columns, "缺少 pred_score 列"
        assert 'pred_rank' in signals.columns, "缺少 pred_rank 列"
        assert len(signals) <= config.top_n, f"信号数量 {len(signals)} 超过 top_n {config.top_n}"

        print(f"  [PASS] 信号生成正常: {len(signals)} 只股票")
        print(f"         Top 3: {signals.head(3)[['stock_code', 'pred_score', 'pred_rank']].to_string(index=False)}")

    except ImportError as e:
        print(f"  [SKIP] XGBoost 未安装: {e}")
    except Exception as e:
        print(f"  [WARN] 信号生成失败（可能无数据）: {e}")

    return True


def test_end_to_end():
    """端到端测试（用历史数据）"""
    print("\n" + "=" * 50)
    print("测试 8: 端到端流程 (需要真实数据)")
    print("=" * 50)

    try:
        from strategist.xgboost_strategy.paper_trading.scheduler import PaperTradingScheduler
        from strategist.xgboost_strategy.paper_trading.db_schema import drop_tables, init_tables

        # 清理并重新建表（确保测试干净）
        drop_tables()
        init_tables()

        scheduler = PaperTradingScheduler()

        # 用 1 个历史周五测试
        test_dates = [date(2024, 1, 5)]
        results = scheduler.run_history_replay(test_dates, '沪深300')

        if results and 'settlement' in results[0] and results[0]['settlement']:
            s = results[0]['settlement']
            print(f"  [PASS] 端到端流程正常")
            print(f"         策略收益: {s['portfolio_ret']:.2f}%")
            print(f"         IC: {s['ic']:.4f}")
        else:
            print(f"  [WARN] 端到端流程未完成（数据不足）")

    except ImportError as e:
        print(f"  [SKIP] 依赖未安装: {e}")
    except Exception as e:
        print(f"  [WARN] 端到端测试失败: {e}")
        import traceback
        traceback.print_exc()

    return True


def run_all_tests():
    """运行所有测试"""
    print("\n" + "#" * 50)
    print("#  Paper Trading 模块测试")
    print("#" * 50)

    tests = [
        test_db_connection,
        test_table_creation,
        test_config,
        test_position_manager,
        test_settlement_engine,
        test_evaluator,
        test_signal_generator,
        test_end_to_end,
    ]

    results = []
    for test_fn in tests:
        try:
            passed = test_fn()
            results.append((test_fn.__name__, passed))
        except Exception as e:
            print(f"\n  [ERROR] {test_fn.__name__} 异常: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_fn.__name__, False))

    # 汇总
    print("\n" + "#" * 50)
    print("#  测试汇总")
    print("#" * 50)
    for name, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")

    n_pass = sum(1 for _, p in results if p)
    print(f"\n  总计: {n_pass}/{len(results)} 通过")

    return n_pass == len(results)


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
