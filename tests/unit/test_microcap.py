# -*- coding: utf-8 -*-
"""
微盘股策略单元测试

覆盖：
- universe.py   : ST 剔除、pe_ttm 过滤、percentile 筛选
- factors.py    : look-ahead bias（EPS/EBIT 日期边界）、因子方向、PEG 计算
- backtest.py   : 买卖顺序、资金守恒、NAV 计算、pnl_pct
- _calc_summary : 夏普、最大回撤、年化收益

使用 unittest.mock 完全 mock 数据库，不依赖真实 DB。
"""
import sys
import os
import unittest
from unittest.mock import patch, MagicMock
from datetime import date

import pandas as pd
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from strategist.microcap.config import MicrocapConfig
from strategist.microcap.backtest import MicrocapBacktest


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_conn_mock(query_results: dict):
    """
    返回一个 mock connection，pd.read_sql 会根据 SQL 关键词返回预设 DataFrame。
    query_results: {关键词: DataFrame}
    """
    conn = MagicMock()
    conn.close = MagicMock()

    def fake_read_sql(sql, conn_, params=None):
        sql_lower = sql.strip().lower()
        for key, df in query_results.items():
            if key.lower() in sql_lower:
                return df
        return pd.DataFrame()

    return conn, fake_read_sql


# ─────────────────────────────────────────────────────────────────────────────
# universe.py
# ─────────────────────────────────────────────────────────────────────────────

class TestGetDailyUniverse(unittest.TestCase):

    def _run_universe(self, db_df, percentile=0.20, exclude_st=True,
                      require_positive_pe=True):
        from strategist.microcap.universe import get_daily_universe
        conn_mock = MagicMock()
        conn_mock.close = MagicMock()
        with patch('strategist.microcap.universe.get_connection', return_value=conn_mock), \
             patch('pandas.read_sql', return_value=db_df):
            return get_daily_universe(
                '2024-01-02', percentile=percentile,
                exclude_st=exclude_st, require_positive_pe=require_positive_pe,
            )

    def test_percentile_selects_bottom_20(self):
        """market_cap_percentile=0.20 应只返回市值最小的 20% 股票"""
        df = pd.DataFrame({
            'stock_code': [f'{i:06d}.SZ' for i in range(1, 11)],
            'pe_ttm': [10.0] * 10,
            'total_mv': list(range(1, 11)),  # 1~10 亿
        })
        result = self._run_universe(df, percentile=0.20)
        # quantile(0.20) of [1..10] = 2.8, so total_mv <= 2.8 => 1,2
        self.assertEqual(len(result), 2)
        self.assertIn('000001.SZ', result)
        self.assertIn('000002.SZ', result)

    def test_exclude_st_joins_on_is_st(self):
        """exclude_st=True 时 SQL 中应包含 JOIN trade_stock_basic"""
        from strategist.microcap import universe as u
        conn_mock = MagicMock()
        conn_mock.close = MagicMock()
        captured_sql = []

        def fake_read_sql(sql, conn_, params=None):
            captured_sql.append(sql)
            return pd.DataFrame({'stock_code': [], 'pe_ttm': [], 'total_mv': []})

        with patch('strategist.microcap.universe.get_connection', return_value=conn_mock), \
             patch('pandas.read_sql', side_effect=fake_read_sql):
            u.get_daily_universe('2024-01-02', exclude_st=True)

        self.assertTrue(any('trade_stock_basic' in s for s in captured_sql),
                        "exclude_st=True 时 SQL 必须 JOIN trade_stock_basic")
        self.assertTrue(any('is_st' in s for s in captured_sql),
                        "exclude_st=True 时 SQL 必须过滤 is_st")

    def test_no_st_filter_skips_join(self):
        """exclude_st=False 时 SQL 不应包含 trade_stock_basic"""
        from strategist.microcap import universe as u
        conn_mock = MagicMock()
        conn_mock.close = MagicMock()
        captured_sql = []

        def fake_read_sql(sql, conn_, params=None):
            captured_sql.append(sql)
            return pd.DataFrame({'stock_code': [], 'pe_ttm': [], 'total_mv': []})

        with patch('strategist.microcap.universe.get_connection', return_value=conn_mock), \
             patch('pandas.read_sql', side_effect=fake_read_sql):
            u.get_daily_universe('2024-01-02', exclude_st=False)

        self.assertFalse(any('trade_stock_basic' in s for s in captured_sql),
                         "exclude_st=False 时不应 JOIN trade_stock_basic")

    def test_require_positive_pe_false_skips_pe_filter(self):
        """require_positive_pe=False 时 WHERE 子句不应含 pe_ttm 过滤条件"""
        from strategist.microcap import universe as u
        conn_mock = MagicMock()
        conn_mock.close = MagicMock()
        captured_params = []

        def fake_read_sql(sql, conn_, params=None):
            captured_params.append((sql, params))
            return pd.DataFrame({'stock_code': [], 'pe_ttm': [], 'total_mv': []})

        with patch('strategist.microcap.universe.get_connection', return_value=conn_mock), \
             patch('pandas.read_sql', side_effect=fake_read_sql):
            u.get_daily_universe('2024-01-02', require_positive_pe=False)

        sql_used = captured_params[0][0]
        # SELECT 子句可以包含 pe_ttm 列，但 WHERE 子句不应有 pe_ttm 过滤条件
        where_clause = sql_used.lower().split('where')[-1] if 'where' in sql_used.lower() else ''
        self.assertNotIn('pe_ttm', where_clause,
                         "require_positive_pe=False 时 WHERE 子句不应含 pe_ttm 过滤条件")

    def test_empty_db_returns_empty_list(self):
        """DB 无数据时返回空列表，不抛异常"""
        result = self._run_universe(pd.DataFrame(
            {'stock_code': [], 'pe_ttm': [], 'total_mv': []}
        ))
        self.assertEqual(result, [])


# ─────────────────────────────────────────────────────────────────────────────
# factors.py — look-ahead bias
# ─────────────────────────────────────────────────────────────────────────────

class TestFactorsNoLookahead(unittest.TestCase):
    """所有因子查询不得使用 CURDATE()，必须以 trade_date 为上界"""

    def _capture_sqls(self, func, trade_date, stock_codes):
        conn_mock = MagicMock()
        conn_mock.close = MagicMock()
        captured = []

        def fake_read_sql(sql, conn_, params=None):
            captured.append((sql, params or []))
            return pd.DataFrame()

        with patch('strategist.microcap.factors.get_connection', return_value=conn_mock), \
             patch('pandas.read_sql', side_effect=fake_read_sql):
            try:
                func(trade_date, stock_codes)
            except Exception:
                pass
        return captured

    def _assert_no_curdate(self, sqls, func_name):
        for sql, _ in sqls:
            self.assertNotIn('curdate()', sql.lower(),
                             f"{func_name} SQL 含 CURDATE()，存在前视偏差！")

    def _assert_trade_date_in_params(self, sqls, trade_date, func_name):
        """trade_date 必须作为参数传入，用于限制报告期上界"""
        all_params = [str(p) for _, params in sqls for p in params]
        self.assertIn(trade_date, all_params,
                      f"{func_name} 未将 trade_date 作为查询参数传入")

    def test_calc_peg_no_curdate(self):
        from strategist.microcap.factors import calc_peg
        sqls = self._capture_sqls(calc_peg, '2022-06-30', ['000001.SZ'])
        self._assert_no_curdate(sqls, 'calc_peg')
        self._assert_trade_date_in_params(sqls, '2022-06-30', 'calc_peg')

    def test_calc_peg_ebit_mv_no_curdate(self):
        from strategist.microcap.factors import calc_peg_ebit_mv
        sqls = self._capture_sqls(calc_peg_ebit_mv, '2022-06-30', ['000001.SZ'])
        self._assert_no_curdate(sqls, 'calc_peg_ebit_mv')
        self._assert_trade_date_in_params(sqls, '2022-06-30', 'calc_peg_ebit_mv')

    def test_calc_roe_no_curdate(self):
        from strategist.microcap.factors import calc_roe
        sqls = self._capture_sqls(calc_roe, '2022-06-30', ['000001.SZ'])
        self._assert_no_curdate(sqls, 'calc_roe')

    def test_calc_ebit_ratio_no_curdate(self):
        from strategist.microcap.factors import calc_ebit_ratio
        sqls = self._capture_sqls(calc_ebit_ratio, '2022-06-30', ['000001.SZ'])
        self._assert_no_curdate(sqls, 'calc_ebit_ratio')


class TestCalcPeg(unittest.TestCase):
    """PEG 因子计算逻辑"""

    def _run_peg(self, pe_df, eps_df, trade_date='2024-01-02'):
        from strategist.microcap.factors import calc_peg
        conn_mock = MagicMock()
        conn_mock.close = MagicMock()
        call_count = [0]

        def fake_read_sql(sql, conn_, params=None):
            call_count[0] += 1
            if 'pe_ttm' in sql.lower() and 'financial' not in sql.lower():
                return pe_df
            return eps_df

        with patch('strategist.microcap.factors.get_connection', return_value=conn_mock), \
             patch('pandas.read_sql', side_effect=fake_read_sql):
            return calc_peg(trade_date, ['000001.SZ', '000002.SZ'])

    def test_peg_positive_growth(self):
        """PE=20, EPS从1增长到2 => growth=100%, PEG=20/100=0.2"""
        pe_df = pd.DataFrame({'stock_code': ['000001.SZ'], 'pe_ttm': [20.0]})
        eps_df = pd.DataFrame({
            'stock_code': ['000001.SZ', '000001.SZ'],
            'report_year': [2023, 2022],
            'eps': [2.0, 1.0],
        })
        result = self._run_peg(pe_df, eps_df)
        row = result[result['stock_code'] == '000001.SZ']
        self.assertFalse(row.empty)
        self.assertAlmostEqual(float(row['peg'].iloc[0]), 0.2, places=4)

    def test_peg_negative_growth_returns_nan(self):
        """EPS 负增长时 PEG 应为 NaN（增速为负，PEG无意义）"""
        pe_df = pd.DataFrame({'stock_code': ['000001.SZ'], 'pe_ttm': [20.0]})
        eps_df = pd.DataFrame({
            'stock_code': ['000001.SZ', '000001.SZ'],
            'report_year': [2023, 2022],
            'eps': [0.5, 1.0],   # 下降
        })
        result = self._run_peg(pe_df, eps_df)
        row = result[result['stock_code'] == '000001.SZ']
        # PEG = 20 / (-50 * 100) < 0，应被过滤为 NaN
        if not row.empty:
            self.assertTrue(pd.isna(row['peg'].iloc[0]),
                            "负增速时 PEG 应为 NaN")

    def test_peg_no_eps_fallback_to_pe(self):
        """无 EPS 数据时，应退化为 PE_TTM"""
        pe_df = pd.DataFrame({'stock_code': ['000001.SZ'], 'pe_ttm': [15.0]})
        eps_df = pd.DataFrame({'stock_code': [], 'report_year': [], 'eps': []})
        result = self._run_peg(pe_df, eps_df)
        row = result[result['stock_code'] == '000001.SZ']
        self.assertFalse(row.empty)
        self.assertAlmostEqual(float(row['peg'].iloc[0]), 15.0, places=4)


class TestCalcRoe(unittest.TestCase):
    def test_roe_negated_for_ascending_sort(self):
        """ROE 越高越好，返回值应取负，确保 sort_values 升序能选出最高 ROE"""
        from strategist.microcap.factors import calc_roe
        conn_mock = MagicMock()
        conn_mock.close = MagicMock()
        roe_df = pd.DataFrame({
            'stock_code': ['000001.SZ', '000002.SZ'],
            'roe_val': [0.30, 0.15],
        })

        with patch('strategist.microcap.factors.get_connection', return_value=conn_mock), \
             patch('pandas.read_sql', return_value=roe_df):
            result = calc_roe('2024-01-02', ['000001.SZ', '000002.SZ'])

        # 000001 ROE 更高，其 roe 列值应更小（取负后）
        r1 = float(result[result['stock_code'] == '000001.SZ']['roe'].iloc[0])
        r2 = float(result[result['stock_code'] == '000002.SZ']['roe'].iloc[0])
        self.assertLess(r1, r2, "ROE 越高，返回的负值应越小（升序排名靠前）")


# ─────────────────────────────────────────────────────────────────────────────
# backtest.py
# ─────────────────────────────────────────────────────────────────────────────

class TestMicrocapBacktest(unittest.TestCase):

    def _make_config(self, hold_days=1, factor='pure_mv', top_n=2):
        return MicrocapConfig(
            start_date='2024-01-01',
            end_date='2024-01-10',
            factor=factor,
            top_n=top_n,
            hold_days=hold_days,
            buy_cost_rate=0.0,
            sell_cost_rate=0.0,
            slippage_rate=0.0,
        )

    def _run_with_mocks(self, config, trade_dates, price_map, selected_stocks):
        """
        trade_dates: ['2024-01-02', '2024-01-03', ...]
        price_map:   {'2024-01-02': {'open': {'A': 10.0}, 'close': {'A': 10.5}}, ...}
        selected_stocks: {'2024-01-02': ['A', 'B'], ...}
        """
        bt = MicrocapBacktest(config)

        dates_df = pd.DataFrame({'trade_date': trade_dates})

        def mock_get_trade_dates(start, end):
            return trade_dates

        def mock_select_stocks(trade_date):
            return selected_stocks.get(trade_date, [])

        def mock_load_prices(trade_date):
            bt._price_cache[trade_date] = price_map.get(
                trade_date, {'open': {}, 'close': {}}
            )

        bt._get_trade_dates = mock_get_trade_dates
        bt._select_stocks = mock_select_stocks
        bt._load_prices_for_date = mock_load_prices

        return bt.run()

    def test_sell_before_buy_same_day(self):
        """hold_days=1：T 日买入，T+1 日必须先卖后买，cash 不应为负"""
        config = self._make_config(hold_days=1, top_n=2)
        dates = ['2024-01-02', '2024-01-03', '2024-01-04']
        prices = {d: {'open': {'A': 10.0, 'B': 10.0},
                      'close': {'A': 10.0, 'B': 10.0}} for d in dates}
        selected = {'2024-01-02': ['A', 'B'], '2024-01-03': ['A', 'B']}

        result = self._run_with_mocks(config, dates, prices, selected)
        self.assertEqual(result['status'], 'ok')
        for row in result['daily_values_df'].to_dict('records'):
            self.assertGreaterEqual(row['cash'], -1e-9,
                                    f"cash 不应为负: {row}")

    def test_nav_conservation(self):
        """无手续费无滑点时，NAV 应等于 cash + holdings 市值，总和守恒"""
        config = self._make_config(hold_days=2, top_n=1)
        dates = ['2024-01-02', '2024-01-03', '2024-01-04', '2024-01-05']
        prices = {d: {'open': {'A': 10.0}, 'close': {'A': 10.0}} for d in dates}
        selected = {'2024-01-02': ['A']}

        result = self._run_with_mocks(config, dates, prices, selected)
        self.assertEqual(result['status'], 'ok')
        # 无成本无价格变化，NAV 应始终 ~= 1.0
        for row in result['daily_values_df'].to_dict('records'):
            self.assertAlmostEqual(row['nav'], 1.0, places=6,
                                   msg=f"无成本时 NAV 应守恒: {row}")

    def test_price_appreciation(self):
        """
        T=01-02 选股A；T+1=01-03 开盘10买入，收盘10盯市；
        T+2=01-04 开盘11卖出 => NAV 应 ~= 1.1
        """
        config = self._make_config(hold_days=1, top_n=1)
        dates = ['2024-01-02', '2024-01-03', '2024-01-04']
        prices = {
            # 选股日：价格不影响执行
            '2024-01-02': {'open': {'A': 10.0}, 'close': {'A': 10.0}},
            # T+1 买入日：开盘10买入
            '2024-01-03': {'open': {'A': 10.0}, 'close': {'A': 10.0}},
            # T+2 卖出日：开盘11卖出
            '2024-01-04': {'open': {'A': 11.0}, 'close': {'A': 11.0}},
        }
        selected = {'2024-01-02': ['A']}
        result = self._run_with_mocks(config, dates, prices, selected)
        self.assertEqual(result['status'], 'ok')
        final_nav = result['daily_values_df'].iloc[-1]['nav']
        self.assertAlmostEqual(final_nav, 1.1, places=5)

    def test_costs_reduce_nav(self):
        """有手续费时，即使价格不变，NAV 也应小于1"""
        config = MicrocapConfig(
            start_date='2024-01-01', end_date='2024-01-10',
            factor='pure_mv', top_n=1, hold_days=1,
            buy_cost_rate=0.001, sell_cost_rate=0.001, slippage_rate=0.0,
        )
        dates = ['2024-01-02', '2024-01-03', '2024-01-04']
        prices = {d: {'open': {'A': 10.0}, 'close': {'A': 10.0}} for d in dates}
        selected = {'2024-01-02': ['A']}
        result = self._run_with_mocks(config, dates, prices, selected)
        self.assertEqual(result['status'], 'ok')
        final_nav = result['daily_values_df'].iloc[-1]['nav']
        self.assertLess(final_nav, 1.0, "有手续费时 NAV 应小于1")

    def test_skip_already_held_stocks(self):
        """已持有的股票不应被重复买入（防止仓位覆盖）"""
        config = self._make_config(hold_days=3, top_n=1)
        dates = ['2024-01-02', '2024-01-03', '2024-01-04',
                 '2024-01-05', '2024-01-08']
        prices = {d: {'open': {'A': 10.0}, 'close': {'A': 10.0}} for d in dates}
        # 每天都选 A，但 A 持有期 3 天
        selected = {d: ['A'] for d in dates}
        result = self._run_with_mocks(config, dates, prices, selected)
        self.assertEqual(result['status'], 'ok')
        # 任意一天持仓数不应超过 1
        for row in result['daily_values_df'].to_dict('records'):
            self.assertLessEqual(row['n_holdings'], 1,
                                 f"持仓不应超过 top_n=1: {row}")


# ─────────────────────────────────────────────────────────────────────────────
# _calc_summary
# ─────────────────────────────────────────────────────────────────────────────

class TestCalcSummary(unittest.TestCase):

    def _summary(self, navs, returns=None):
        config = MicrocapConfig()
        bt = MicrocapBacktest(config)
        n = len(navs)
        if returns is None:
            returns = [0.0] + [(navs[i] / navs[i-1] - 1) for i in range(1, n)]
        daily_df = pd.DataFrame({
            'trade_date': pd.date_range('2024-01-02', periods=n),
            'nav': navs,
            'daily_return': returns,
        })
        trades_df = pd.DataFrame({
            'return': [0.05, -0.02, 0.03, -0.01, 0.04],
        })
        return bt._calc_summary(trades_df, daily_df)

    def test_total_return(self):
        navs = [1.0, 1.05, 1.10]
        s = self._summary(navs)
        self.assertAlmostEqual(s['total_return'], 0.10, places=5)

    def test_max_drawdown_negative(self):
        """最大回撤应为负数"""
        navs = [1.0, 1.2, 0.9, 1.1]
        s = self._summary(navs)
        self.assertLess(s['max_drawdown'], 0,
                        "max_drawdown 应为负数")
        # 从1.2跌到0.9，回撤 = (0.9-1.2)/1.2 = -0.25
        self.assertAlmostEqual(s['max_drawdown'], -0.25, places=4)

    def test_win_rate(self):
        """5笔中3笔盈利 => 胜率60%"""
        config = MicrocapConfig()
        bt = MicrocapBacktest(config)
        trades_df = pd.DataFrame({'return': [0.05, -0.02, 0.03, -0.01, 0.04]})
        daily_df = pd.DataFrame({
            'trade_date': pd.date_range('2024-01-02', periods=3),
            'nav': [1.0, 1.05, 1.10],
            'daily_return': [0.0, 0.05, 0.047],
        })
        s = bt._calc_summary(trades_df, daily_df)
        self.assertAlmostEqual(s['win_rate'], 0.6, places=4)

    def test_sharpe_positive_for_growing_nav(self):
        """单调上涨的 NAV Sharpe 应为正"""
        navs = [1.0 + i * 0.001 for i in range(50)]
        s = self._summary(navs)
        self.assertGreater(s['sharpe_ratio'], 0)

    def test_annual_return_calculation(self):
        """250 交易日翻倍 => 年化约100%"""
        navs = [1.0 + i * (1.0 / 250) for i in range(251)]
        s = self._summary(navs)
        # final_nav ≈ 2.0, years = 251/250 ≈ 1.004, annual ≈ 2^(1/1.004)-1 ≈ 99.6%
        self.assertGreater(s['annual_return'], 0.9)


if __name__ == '__main__':
    unittest.main(verbosity=2)
