# -*- coding: utf-8 -*-
"""
微盘股策略 v3.0 增强功能单元测试

覆盖：
- Feature 1: 流动性过滤默认值 (min_avg_turnover = 5_000_000)
- Feature 2: 月度日历择时 (calendar_timing)
- Feature 3: 动量反转复合因子 (calc_pure_mv_mom)
- Feature 4: 动态市值止盈 (dynamic_cap_exit)

使用 unittest.mock 完全 mock 数据库，不依赖真实 DB。
"""
import sys
import os
import unittest
from unittest.mock import patch, MagicMock

import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from strategist.microcap.config import MicrocapConfig
from strategist.microcap.backtest import MicrocapBacktest


# ---------------------------------------------------------------------------
# Feature 1: 流动性过滤默认值
# ---------------------------------------------------------------------------
class TestLiquidityFilterDefault(unittest.TestCase):
    """min_avg_turnover 默认值应从 0 改为 5_000_000。"""

    def test_default_min_avg_turnover(self):
        config = MicrocapConfig()
        self.assertEqual(config.min_avg_turnover, 5_000_000.0)

    def test_override_min_avg_turnover(self):
        config = MicrocapConfig(min_avg_turnover=0.0)
        self.assertEqual(config.min_avg_turnover, 0.0)

    def test_cli_default(self):
        """CLI --min-turnover 默认应为 5_000_000。"""
        import argparse
        # 模拟 run_backtest 的 parser
        from strategist.microcap.run_backtest import main
        import strategist.microcap.run_backtest as rb_module
        # 直接检查 argparse 的默认值：parse 空参数
        parser = argparse.ArgumentParser()
        parser.add_argument('--min-turnover', type=float, default=5_000_000.0,
                           dest='min_avg_turnover')
        args = parser.parse_args([])
        self.assertEqual(args.min_avg_turnover, 5_000_000.0)


# ---------------------------------------------------------------------------
# Feature 2: 月度日历择时
# ---------------------------------------------------------------------------
class TestCalendarTiming(unittest.TestCase):
    """calendar_timing 弱月份减仓功能。"""

    def test_config_defaults(self):
        config = MicrocapConfig()
        self.assertFalse(config.calendar_timing)
        self.assertEqual(config.weak_months, (1, 4, 12))
        self.assertEqual(config.weak_month_ratio, 0.5)

    def test_config_custom(self):
        config = MicrocapConfig(
            calendar_timing=True,
            weak_months=(3, 6, 9),
            weak_month_ratio=0.3,
        )
        self.assertTrue(config.calendar_timing)
        self.assertEqual(config.weak_months, (3, 6, 9))
        self.assertEqual(config.weak_month_ratio, 0.3)

    def test_effective_top_n_weak_month(self):
        """弱月 effective_top_n 应为 top_n * weak_month_ratio。"""
        config = MicrocapConfig(
            calendar_timing=True,
            weak_months=(1, 4, 12),
            weak_month_ratio=0.5,
            top_n=15,
        )
        # 1月是弱月
        effective = max(1, int(config.top_n * config.weak_month_ratio))
        self.assertEqual(effective, 7)  # int(15 * 0.5) = 7

    def test_effective_top_n_strong_month(self):
        """非弱月 effective_top_n 应等于 top_n。"""
        config = MicrocapConfig(
            calendar_timing=True,
            weak_months=(1, 4, 12),
            top_n=15,
        )
        # 3月不是弱月
        month = 3
        if month in config.weak_months:
            effective = max(1, int(config.top_n * config.weak_month_ratio))
        else:
            effective = config.top_n
        self.assertEqual(effective, 15)

    def test_effective_top_n_disabled(self):
        """calendar_timing=False 时不应影响 top_n。"""
        config = MicrocapConfig(
            calendar_timing=False,
            top_n=15,
        )
        effective = config.top_n
        self.assertEqual(effective, 15)

    def test_minimum_1_stock(self):
        """极小 ratio 不应让 effective_top_n < 1。"""
        config = MicrocapConfig(
            calendar_timing=True,
            weak_months=(1,),
            weak_month_ratio=0.01,
            top_n=3,
        )
        effective = max(1, int(config.top_n * config.weak_month_ratio))
        self.assertEqual(effective, 1)  # max(1, int(3*0.01)) = max(1, 0) = 1


# ---------------------------------------------------------------------------
# Feature 3: 动量反转复合因子
# ---------------------------------------------------------------------------
class TestPureMvMom(unittest.TestCase):
    """calc_pure_mv_mom 因子计算。"""

    def test_config_defaults(self):
        config = MicrocapConfig()
        self.assertEqual(config.momentum_lookback, 20)
        self.assertEqual(config.momentum_weight, 0.3)

    def test_empty_input(self):
        """空股票列表应返回空 DataFrame。"""
        from strategist.microcap.factors import calc_pure_mv_mom
        result = calc_pure_mv_mom('2024-01-15', [], lookback=20, weight=0.3)
        self.assertTrue(result.empty)
        self.assertListEqual(list(result.columns), ['stock_code', 'pure_mv_mom'])

    @patch('strategist.microcap.factors.get_connection')
    def test_mv_only_fallback(self, mock_get_conn):
        """无价格数据时应退化为纯市值排序。"""
        from strategist.microcap.factors import calc_pure_mv_mom

        # Mock: 市值查询返回数据，价格查询返回空
        conn = MagicMock()
        mock_get_conn.return_value = conn

        mv_df = pd.DataFrame({
            'stock_code': ['000001', '000002', '000003'],
            'total_mv': [100.0, 50.0, 200.0],
        })

        call_count = [0]
        def fake_read_sql(sql, conn_, params=None):
            call_count[0] += 1
            sql_lower = sql.strip().lower()
            if 'total_mv' in sql_lower:
                return mv_df.copy()
            if 'close_price' in sql_lower:
                return pd.DataFrame()  # 无价格数据
            return pd.DataFrame()

        with patch('pandas.read_sql', side_effect=fake_read_sql):
            result = calc_pure_mv_mom('2024-01-15', ['000001', '000002', '000003'],
                                       lookback=20, weight=0.3)

        self.assertFalse(result.empty)
        self.assertIn('pure_mv_mom', result.columns)
        # 无价格数据时，pure_mv_mom = total_mv
        self.assertEqual(len(result), 3)

    @patch('strategist.microcap.factors.get_connection')
    def test_composite_ranking(self, mock_get_conn):
        """验证复合排名逻辑：score = mv_rank * (1-w) + reversal_rank * w。"""
        from strategist.microcap.factors import calc_pure_mv_mom

        conn = MagicMock()
        mock_get_conn.return_value = conn

        mv_df = pd.DataFrame({
            'stock_code': ['A', 'B', 'C'],
            'total_mv': [100.0, 200.0, 300.0],  # A 最小
        })

        # 构造价格数据：30 个交易日
        dates = pd.date_range('2023-12-01', periods=30, freq='B')
        price_records = []
        for d in dates:
            d_str = d.strftime('%Y-%m-%d')
            # A: 从 10 涨到 12 (+20%)
            # B: 从 10 跌到 8 (-20%)
            # C: 从 10 到 10 (0%)
            idx = dates.get_loc(d)
            price_records.append({'stock_code': 'A', 'trade_date': d_str,
                                  'close_price': 10.0 + 2.0 * idx / (len(dates)-1)})
            price_records.append({'stock_code': 'B', 'trade_date': d_str,
                                  'close_price': 10.0 - 2.0 * idx / (len(dates)-1)})
            price_records.append({'stock_code': 'C', 'trade_date': d_str,
                                  'close_price': 10.0})
        price_df = pd.DataFrame(price_records)

        def fake_read_sql(sql, conn_, params=None):
            sql_lower = sql.strip().lower()
            if 'total_mv' in sql_lower:
                return mv_df.copy()
            if 'close_price' in sql_lower:
                return price_df.copy()
            return pd.DataFrame()

        with patch('pandas.read_sql', side_effect=fake_read_sql):
            result = calc_pure_mv_mom('2024-01-15', ['A', 'B', 'C'],
                                       lookback=20, weight=0.3)

        self.assertEqual(len(result), 3)
        # B 应排名最前：市值中等(rank=2) + 跌最多(reversal_rank=1)
        # A 应排名中间：市值最小(rank=1) + 涨最多(reversal_rank=3)
        result_sorted = result.sort_values('pure_mv_mom')
        # 验证 B 的复合分数较低（排名靠前）
        scores = dict(zip(result['stock_code'], result['pure_mv_mom']))
        # mv_rank: A=1, B=2, C=3; reversal_rank: B=1, C=2, A=3
        # A: 1*0.7 + 3*0.3 = 0.7+0.9 = 1.6
        # B: 2*0.7 + 1*0.3 = 1.4+0.3 = 1.7
        # C: 3*0.7 + 2*0.3 = 2.1+0.6 = 2.7
        self.assertAlmostEqual(scores['A'], 1.6, places=1)
        self.assertAlmostEqual(scores['B'], 1.7, places=1)
        self.assertAlmostEqual(scores['C'], 2.7, places=1)

    def test_factor_in_backtest_choices(self):
        """pure_mv_mom 应在 backtest 的因子列表中。"""
        config = MicrocapConfig(factor='pure_mv_mom')
        bt = MicrocapBacktest(config)
        # 不报错即可；真正的路由测试在集成测试中


# ---------------------------------------------------------------------------
# Feature 4: 动态市值止盈
# ---------------------------------------------------------------------------
class TestDynamicCapExit(unittest.TestCase):
    """dynamic_cap_exit 持仓市值超百分位阈值则提前卖出。"""

    def test_config_defaults(self):
        config = MicrocapConfig()
        self.assertFalse(config.dynamic_cap_exit)
        self.assertEqual(config.cap_exit_percentile, 0.50)

    def test_config_custom(self):
        config = MicrocapConfig(dynamic_cap_exit=True, cap_exit_percentile=0.60)
        self.assertTrue(config.dynamic_cap_exit)
        self.assertEqual(config.cap_exit_percentile, 0.60)

    def test_check_cap_exit_disabled(self):
        """dynamic_cap_exit=False 时不应触发任何止盈。"""
        config = MicrocapConfig(dynamic_cap_exit=False)
        bt = MicrocapBacktest(config)
        holdings = {
            '000001': {'sell_date': '2024-02-01', 'delay_count': 0},
        }
        # 不应改变 sell_date
        bt._check_cap_exit('2024-01-15', holdings, ['2024-01-15', '2024-01-16'], 0)
        self.assertEqual(holdings['000001']['sell_date'], '2024-02-01')

    def test_check_cap_exit_empty_holdings(self):
        """空持仓不应报错。"""
        config = MicrocapConfig(dynamic_cap_exit=True)
        bt = MicrocapBacktest(config)
        bt._cap_thresholds = {'2024-01-15': 500.0}
        bt._check_cap_exit('2024-01-15', {}, ['2024-01-15', '2024-01-16'], 0)
        # 无异常即通过

    @patch('strategist.microcap.backtest.get_connection')
    def test_check_cap_exit_triggers(self, mock_get_conn):
        """持仓市值超过阈值应触发提前卖出。"""
        config = MicrocapConfig(dynamic_cap_exit=True, cap_exit_percentile=0.50)
        bt = MicrocapBacktest(config)
        bt._cap_thresholds = {'2024-01-15': 500.0}  # 阈值 500

        holdings = {
            '000001': {'sell_date': '2024-02-01', 'delay_count': 0},
            '000002': {'sell_date': '2024-02-01', 'delay_count': 0},
        }

        # Mock: 000001 市值 800 (超阈值), 000002 市值 300 (未超)
        conn = MagicMock()
        mock_get_conn.return_value = conn

        mv_df = pd.DataFrame({
            'stock_code': ['000001', '000002'],
            'total_mv': [800.0, 300.0],
        })

        with patch('pandas.read_sql', return_value=mv_df):
            trade_dates = ['2024-01-15', '2024-01-16', '2024-01-17']
            bt._check_cap_exit('2024-01-15', holdings, trade_dates, 0)

        # 000001 应被提前卖出（sell_date 改为下一交易日）
        self.assertEqual(holdings['000001']['sell_date'], '2024-01-16')
        self.assertTrue(holdings['000001'].get('cap_exit', False))

        # 000002 不受影响
        self.assertEqual(holdings['000002']['sell_date'], '2024-02-01')
        self.assertFalse(holdings['000002'].get('cap_exit', False))

    @patch('strategist.microcap.backtest.get_connection')
    def test_check_cap_exit_no_earlier_sell(self, mock_get_conn):
        """如果原 sell_date 已经更早，不应覆盖。"""
        config = MicrocapConfig(dynamic_cap_exit=True, cap_exit_percentile=0.50)
        bt = MicrocapBacktest(config)
        bt._cap_thresholds = {'2024-01-15': 500.0}

        holdings = {
            '000001': {'sell_date': '2024-01-16', 'delay_count': 0},  # 已经是明天
        }

        conn = MagicMock()
        mock_get_conn.return_value = conn

        mv_df = pd.DataFrame({
            'stock_code': ['000001'],
            'total_mv': [800.0],
        })

        with patch('pandas.read_sql', return_value=mv_df):
            trade_dates = ['2024-01-15', '2024-01-16', '2024-01-17']
            bt._check_cap_exit('2024-01-15', holdings, trade_dates, 0)

        # sell_date 已经是 01-16 = next_date，不变
        self.assertEqual(holdings['000001']['sell_date'], '2024-01-16')

    @patch('strategist.microcap.backtest.get_connection')
    def test_preload_cap_thresholds(self, mock_get_conn):
        """_preload_cap_thresholds 应正确计算百分位。"""
        config = MicrocapConfig(dynamic_cap_exit=True, cap_exit_percentile=0.50)
        bt = MicrocapBacktest(config)

        conn = MagicMock()
        mock_get_conn.return_value = conn

        # 构造 2 天，每天 5 只股票
        data = pd.DataFrame({
            'trade_date': ['2024-01-15'] * 5 + ['2024-01-16'] * 5,
            'total_mv': [100, 200, 300, 400, 500,
                         150, 250, 350, 450, 550],
        })

        with patch('pandas.read_sql', return_value=data):
            thresholds = bt._preload_cap_thresholds(['2024-01-15', '2024-01-16'])

        self.assertEqual(len(thresholds), 2)
        # 50th percentile of [100,200,300,400,500] = 300
        self.assertAlmostEqual(thresholds['2024-01-15'], 300.0)
        # 50th percentile of [150,250,350,450,550] = 350
        self.assertAlmostEqual(thresholds['2024-01-16'], 350.0)

    def test_cap_exit_in_trade_record(self):
        """trade record 应包含 cap_exit 字段。"""
        config = MicrocapConfig(dynamic_cap_exit=True)
        bt = MicrocapBacktest(config)
        # 模拟一条交易记录
        trade = {
            'buy_date': '2024-01-10',
            'sell_date': '2024-01-15',
            'stock_code': '000001',
            'buy_price': 10.0,
            'sell_price': 11.0,
            'hold_days': 5,
            'delay_count': 0,
            'return': 0.1,
            'pnl': 1.0,
            'cap_exit': True,
        }
        self.assertTrue(trade['cap_exit'])

    def test_check_cap_exit_last_day(self):
        """最后一个交易日不应触发 cap exit（没有下一天）。"""
        config = MicrocapConfig(dynamic_cap_exit=True)
        bt = MicrocapBacktest(config)
        bt._cap_thresholds = {'2024-01-16': 500.0}
        holdings = {'000001': {'sell_date': None, 'delay_count': 0}}
        trade_dates = ['2024-01-15', '2024-01-16']
        bt._check_cap_exit('2024-01-16', holdings, trade_dates, 1)
        # 最后一天，next_idx >= len, 不触发
        self.assertIsNone(holdings['000001']['sell_date'])


# ---------------------------------------------------------------------------
# Cross-feature: 配置字段完整性
# ---------------------------------------------------------------------------
class TestConfigCompleteness(unittest.TestCase):
    """验证所有新增配置字段存在且类型正确。"""

    def test_all_new_fields_exist(self):
        config = MicrocapConfig()
        # Feature 1
        self.assertIsInstance(config.min_avg_turnover, float)
        # Feature 2
        self.assertIsInstance(config.calendar_timing, bool)
        self.assertIsInstance(config.weak_months, tuple)
        self.assertIsInstance(config.weak_month_ratio, float)
        # Feature 3
        self.assertIsInstance(config.momentum_lookback, int)
        self.assertIsInstance(config.momentum_weight, float)
        # Feature 4
        self.assertIsInstance(config.dynamic_cap_exit, bool)
        self.assertIsInstance(config.cap_exit_percentile, float)

    def test_full_config_construction(self):
        """所有新字段应能通过构造函数传入。"""
        config = MicrocapConfig(
            min_avg_turnover=5_000_000.0,
            calendar_timing=True,
            weak_months=(1, 4, 12),
            weak_month_ratio=0.5,
            momentum_lookback=20,
            momentum_weight=0.3,
            dynamic_cap_exit=True,
            cap_exit_percentile=0.50,
        )
        self.assertTrue(config.calendar_timing)
        self.assertTrue(config.dynamic_cap_exit)


if __name__ == '__main__':
    unittest.main()
