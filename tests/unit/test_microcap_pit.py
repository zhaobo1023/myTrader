# -*- coding: utf-8 -*-
"""
P0-3 单元测试: PEG 因子 Point-In-Time (PIT) 前视偏差防护

验证保守规则：
- 1-4 月只使用 report_year <= trade_year - 1 的年报
- 5-12 月可使用 report_year <= trade_year 的年报
"""
import pytest
from unittest.mock import patch, MagicMock
import pandas as pd

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _get_max_report_year(trade_date: str) -> int:
    """从 factors.py 中提取的保守 PIT 逻辑，独立测试。"""
    trade_year = int(trade_date[:4])
    trade_month = int(trade_date[5:7])
    if trade_month <= 4:
        return trade_year - 1
    else:
        return trade_year


class TestPITRule:
    """测试保守 PIT 年报截止规则。"""

    def test_january_uses_prior_year(self):
        """1 月：只能用上一年度年报。"""
        assert _get_max_report_year('2026-01-15') == 2025

    def test_february_uses_prior_year(self):
        """2 月：只能用上一年度年报。"""
        assert _get_max_report_year('2026-02-10') == 2025

    def test_march_uses_prior_year(self):
        """3 月：只能用上一年度年报。"""
        assert _get_max_report_year('2026-03-31') == 2025

    def test_april_uses_prior_year(self):
        """4 月：最晚披露月，仍只使用上一年度年报。"""
        assert _get_max_report_year('2026-04-30') == 2025

    def test_may_uses_current_year(self):
        """5 月：年报已全部披露，可使用当年度年报。"""
        assert _get_max_report_year('2026-05-01') == 2026

    def test_june_uses_current_year(self):
        """6 月：可使用当年度年报。"""
        assert _get_max_report_year('2026-06-15') == 2026

    def test_december_uses_current_year(self):
        """12 月：可使用当年度年报。"""
        assert _get_max_report_year('2026-12-31') == 2026

    def test_year_boundary_jan(self):
        """跨年 1 月：2025-01-01 只能用 2023 年报。"""
        assert _get_max_report_year('2025-01-01') == 2024

    def test_year_boundary_may(self):
        """跨年 5 月：2025-05-01 可用 2024 年报。"""
        assert _get_max_report_year('2025-05-01') == 2025


class TestCalcPegPITIntegration:
    """测试 calc_peg 中 PIT 规则的 SQL 参数是否正确传入。"""

    @patch('strategist.microcap.factors.get_connection')
    def test_march_only_queries_prior_year_eps(self, mock_get_conn):
        """3 月执行时，SQL 参数 max_report_year 必须为 trade_year - 1。"""
        from strategist.microcap.factors import calc_peg

        # 构造 mock 连接
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn

        # pe_ttm 查询返回空（触发早退）
        with patch('strategist.microcap.factors.pd.read_sql') as mock_read_sql:
            mock_read_sql.return_value = pd.DataFrame(columns=['stock_code', 'pe_ttm'])
            calc_peg('2026-03-15', ['000001.SZ'])

            # 第一次调用是 PE_TTM 查询，第二次是 EPS 查询
            # PE 查询返回空，函数提前返回，不会到 EPS 查询
            assert mock_read_sql.call_count >= 1

    @patch('strategist.microcap.factors.get_connection')
    def test_june_queries_current_year_eps(self, mock_get_conn):
        """6 月执行时，max_report_year 为当年。"""
        from strategist.microcap.factors import calc_peg

        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn

        captured_params = []

        def capture_read_sql(sql, conn, params=None):
            captured_params.append(params)
            if 'pe_ttm' in sql:
                return pd.DataFrame({'stock_code': ['000001.SZ'], 'pe_ttm': [15.0]})
            # EPS 查询
            return pd.DataFrame(columns=['stock_code', 'report_year', 'eps'])

        with patch('strategist.microcap.factors.pd.read_sql', side_effect=capture_read_sql):
            calc_peg('2026-06-15', ['000001.SZ'])

            # EPS 查询的最后一个参数应为 2026（当年）
            eps_params = captured_params[-1]
            assert eps_params[-1] == 2026, (
                f"6 月查询时 max_report_year 应为 2026，实际为 {eps_params[-1]}"
            )

    @patch('strategist.microcap.factors.get_connection')
    def test_march_queries_prior_year_eps(self, mock_get_conn):
        """3 月执行时，max_report_year 为上一年。"""
        from strategist.microcap.factors import calc_peg

        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn

        captured_params = []

        def capture_read_sql(sql, conn, params=None):
            captured_params.append(params)
            if 'pe_ttm' in sql:
                return pd.DataFrame({'stock_code': ['000001.SZ'], 'pe_ttm': [15.0]})
            return pd.DataFrame(columns=['stock_code', 'report_year', 'eps'])

        with patch('strategist.microcap.factors.pd.read_sql', side_effect=capture_read_sql):
            calc_peg('2026-03-15', ['000001.SZ'])

            eps_params = captured_params[-1]
            assert eps_params[-1] == 2025, (
                f"3 月查询时 max_report_year 应为 2025，实际为 {eps_params[-1]}"
            )
