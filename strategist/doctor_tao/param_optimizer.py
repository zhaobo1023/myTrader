# -*- coding: utf-8 -*-
"""
Step 5: 参数优化与过拟合检查

实现网格搜索参数优化，并进行样本外测试验证
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from datetime import datetime
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from backtest import BacktestEngine


class ParamOptimizer:
    """参数优化器"""

    def __init__(self):
        pass

    def grid_search(
        self,
        param_grid: Dict[str, List],
        start_date: str = '2020-01-01',
        end_date: str = '2023-12-31',
        sample_interval: int = 30
    ) -> pd.DataFrame:
        """
        网格搜索参数优化

        Args:
            param_grid: 参数网格，如 {'hold_days': [40, 60, 80], 'rps_threshold': [85, 90, 95]}
            start_date: 回测开始日期
            end_date: 回测结束日期
            sample_interval: 采样间隔

        Returns:
            参数组合及结果DataFrame
        """
        print("=" * 60)
        print("Step 5: 参数网格搜索")
        print("=" * 60)

        # 生成所有参数组合
        from itertools import product
        keys = param_grid.keys()
        values = param_grid.values()
        combinations = list(product(*values))

        print(f"\n参数组合数: {len(combinations)}")

        results = []

        for idx, combo in enumerate(combinations, 1):
            params = dict(zip(keys, combo))
            print(f"\n[{idx}/{len(combinations)}] 测试参数: {params}")

            # 创建回测引擎
            hold_days = params.get('hold_days', 60)
            rps_exit = params.get('rps_exit_threshold', 85)

            engine = BacktestEngine(hold_days=hold_days, rps_exit_threshold=rps_exit)

            # 运行回测
            try:
                backtest_df, metrics = engine.run_backtest(
                    start_date=start_date,
                    end_date=end_date,
                    sample_interval=sample_interval
                )

                # 记录结果
                result = params.copy()
                result.update(metrics)
                results.append(result)

                print(f"  胜率: {metrics.get('胜率(%)', 0):.2f}%")
                print(f"  平均收益: {metrics.get('平均收益率(%)', 0):.2f}%")

            except Exception as e:
                print(f"  测试失败: {e}")

        # 转换为DataFrame
        results_df = pd.DataFrame(results)

        # 按胜率排序
        if '胜率(%)' in results_df.columns:
            results_df = results_df.sort_values('胜率(%)', ascending=False)

        # 保存结果
        output_dir = os.path.join(ROOT, 'output', 'doctor_tao')
        os.makedirs(output_dir, exist_ok=True)

        output_file = os.path.join(output_dir, f"param_search_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
        results_df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"\n参数搜索结果已保存到: {output_file}")

        # 显示最优参数
        if len(results_df) > 0:
            print("\n" + "=" * 60)
            print("最优参数组合:")
            print("=" * 60)
            print(results_df.head(1).to_string())

        return results_df

    def out_of_sample_test(
        self,
        best_params: Dict,
        train_start: str = '2020-01-01',
        train_end: str = '2023-12-31',
        test_start: str = '2024-01-01',
        test_end: str = '2024-12-31'
    ) -> Tuple[Dict, Dict]:
        """
        样本外测试

        Args:
            best_params: 最优参数
            train_start: 训练期开始日期
            train_end: 训练期结束日期
            test_start: 测试期开始日期
            test_end: 测试期结束日期

        Returns:
            (训练期指标, 测试期指标)
        """
        print("\n" + "=" * 60)
        print("Step 5: 样本外测试")
        print("=" * 60)

        hold_days = best_params.get('hold_days', 60)
        rps_exit = best_params.get('rps_exit_threshold', 85)

        engine = BacktestEngine(hold_days=hold_days, rps_exit_threshold=rps_exit)

        # 训练期回测
        print("\n[1/2] 训练期回测...")
        _, train_metrics = engine.run_backtest(
            start_date=train_start,
            end_date=train_end,
            sample_interval=30
        )

        # 测试期回测
        print("\n[2/2] 测试期回测...")
        _, test_metrics = engine.run_backtest(
            start_date=test_start,
            end_date=test_end,
            sample_interval=30
        )

        # 对比结果
        print("\n" + "=" * 60)
        print("样本外测试对比:")
        print("=" * 60)
        print(f"{'指标':<20} {'训练期':>15} {'测试期':>15} {'差异':>15}")
        print("-" * 60)

        all_keys = set(train_metrics.keys()) | set(test_metrics.keys())
        for key in sorted(all_keys):
            train_val = train_metrics.get(key, 'N/A')
            test_val = test_metrics.get(key, 'N/A')

            if isinstance(train_val, (int, float)) and isinstance(test_val, (int, float)):
                diff = test_val - train_val
                print(f"{key:<20} {train_val:>15.2f} {test_val:>15.2f} {diff:>15.2f}")
            else:
                print(f"{key:<20} {train_val:>15} {test_val:>15}")

        # 判断是否过拟合
        train_win_rate = train_metrics.get('胜率(%)', 0)
        test_win_rate = test_metrics.get('胜率(%)', 0)

        if abs(train_win_rate - test_win_rate) > 10:
            print("\n⚠️ 警告: 训练期和测试期胜率差异 > 10%，可能存在过拟合")
        else:
            print("\n✓ 训练期和测试期表现稳定，无明显过拟合")

        return train_metrics, test_metrics


if __name__ == '__main__':
    # 测试参数优化
    optimizer = ParamOptimizer()

    # 定义参数网格
    param_grid = {
        'hold_days': [40, 60],
        'rps_exit_threshold': [80, 85]
    }

    # 运行网格搜索
    results_df = optimizer.grid_search(
        param_grid=param_grid,
        start_date='2023-01-01',
        end_date='2024-06-30',
        sample_interval=60
    )

    if len(results_df) > 0:
        # 获取最优参数
        best_params = results_df.iloc[0].to_dict()
        print(f"\n最优参数: {best_params}")

        # 样本外测试
        train_metrics, test_metrics = optimizer.out_of_sample_test(
            best_params=best_params,
            train_start='2023-01-01',
            train_end='2024-06-30',
            test_start='2024-07-01',
            test_end='2024-12-31'
        )
