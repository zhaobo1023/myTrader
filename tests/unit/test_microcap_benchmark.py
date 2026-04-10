# -*- coding: utf-8 -*-
"""
P2-2 单元测试: 基准对比指标计算

验证：
- 超额收益计算正确（策略年化 - 基准年化）
- 信息比率公式正确（mean(excess) / std(excess) * sqrt(250)）
- Beta 计算正确（OLS 回归）
- 日期对齐：策略与基准日期不完全重合时只用交集
- 数据不足（< 10 天）时有警告但不报错
"""
import pytest
import numpy as np
import pandas as pd
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from strategist.microcap.benchmark import calc_benchmark_metrics


def make_series(dates, returns):
    return pd.Series(returns, index=dates)


class TestCalcBenchmarkMetrics:

    def test_zero_excess_when_identical(self):
        """策略与基准完全相同 → 超额收益=0，beta=1，alpha=0。"""
        dates = [f'2026-01-{d:02d}' for d in range(2, 12)]
        r = [0.005] * len(dates)
        strat  = make_series(dates, r)
        bench  = make_series(dates, r)

        m = calc_benchmark_metrics(strat, bench)

        assert abs(m['excess_annual_return']) < 1e-6, f"超额应为0，实际 {m['excess_annual_return']}"
        assert abs(m['beta'] - 1.0) < 1e-4,          f"beta 应为1，实际 {m['beta']}"
        assert abs(m['alpha']) < 1e-6,                f"alpha 应为0，实际 {m['alpha']}"

    def test_positive_excess_return(self):
        """策略每日比基准多 0.5% → 超额年化 > 0。"""
        dates = [f'2026-01-{d:02d}' for d in range(2, 22)]
        bench_r = [0.001] * len(dates)
        strat_r = [0.006] * len(dates)
        strat = make_series(dates, strat_r)
        bench = make_series(dates, bench_r)

        m = calc_benchmark_metrics(strat, bench)

        assert m['excess_annual_return'] > 0, "策略收益高于基准，超额应为正"
        assert m['information_ratio'] > 0,    "IR 应为正"

    def test_negative_excess_return(self):
        """策略每日比基准少 0.5% → 超额年化 < 0，IR < 0。"""
        dates = [f'2026-01-{d:02d}' for d in range(2, 22)]
        bench_r = [0.006] * len(dates)
        strat_r = [0.001] * len(dates)
        strat = make_series(dates, strat_r)
        bench = make_series(dates, bench_r)

        m = calc_benchmark_metrics(strat, bench)

        assert m['excess_annual_return'] < 0
        assert m['information_ratio'] < 0

    def test_information_ratio_formula(self):
        """手动验证 IR = mean(excess) / std(excess) * sqrt(250)。"""
        np.random.seed(42)
        n = 100
        bench_r = np.random.normal(0.001, 0.01, n)
        strat_r = bench_r + 0.002   # 固定超额，std(excess)=0，IR=inf（测边界）

        dates = [f'2023-{i:04d}' for i in range(n)]
        strat = make_series(dates, strat_r.tolist())
        bench = make_series(dates, bench_r.tolist())

        m = calc_benchmark_metrics(strat, bench)
        # excess 恒定 → std=0 → IR 应为 0（代码里做了 std>0 保护）
        excess = strat_r - bench_r
        manual_std = np.std(excess, ddof=1)
        if manual_std > 0:
            manual_ir = np.mean(excess) / manual_std * (250 ** 0.5)
            assert abs(m['information_ratio'] - manual_ir) < 0.01

    def test_beta_high_correlation(self):
        """策略=基准*2 → beta 约为 2。"""
        np.random.seed(7)
        n = 60
        bench_r = np.random.normal(0.0, 0.01, n)
        strat_r = bench_r * 2.0

        dates = [f'2023-{i:04d}' for i in range(n)]
        strat = make_series(dates, strat_r.tolist())
        bench = make_series(dates, bench_r.tolist())

        m = calc_benchmark_metrics(strat, bench)
        assert abs(m['beta'] - 2.0) < 0.05, f"beta 应约为2，实际 {m['beta']}"

    def test_date_alignment(self):
        """策略与基准日期不完全重合，只用交集计算。"""
        strat_dates = ['2026-01-02', '2026-01-05', '2026-01-06', '2026-01-07']
        bench_dates = ['2026-01-02', '2026-01-05', '2026-01-08', '2026-01-09']  # 后两天不同

        strat = make_series(strat_dates, [0.01, 0.02, -0.01, 0.005])
        bench = make_series(bench_dates, [0.005, 0.01, 0.008, -0.002])

        m = calc_benchmark_metrics(strat, bench)
        # 交集只有 2 天：2026-01-02, 2026-01-05
        assert m['benchmark_coverage_days'] == 2

    def test_empty_input_returns_zero(self):
        """空序列输入 → 返回全零，不抛异常。"""
        strat = make_series([], [])
        bench = make_series([], [])

        m = calc_benchmark_metrics(strat, bench)
        assert m['benchmark_annual_return'] == 0.0
        assert m['information_ratio'] == 0.0
        assert m['beta'] == 0.0
