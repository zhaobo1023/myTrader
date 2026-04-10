# -*- coding: utf-8 -*-
"""
P1-2 单元测试: 成交额流动性过滤

验证：
- min_avg_turnover=0 时不过滤（保持原行为）
- min_avg_turnover>0 时剔除低流动性股票
- 成交额数据不足（少于 3 日）的股票被剔除
"""
import pytest
from unittest.mock import patch, MagicMock, call
import pandas as pd
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def _make_basic_df(codes, mvs):
    """构造 trade_stock_daily_basic 模拟数据。"""
    return pd.DataFrame({
        'stock_code': codes,
        'pe_ttm':     [15.0] * len(codes),
        'total_mv':   mvs,
    })


def _make_turnover_df(codes, amounts):
    """构造成交额均值模拟数据。"""
    return pd.DataFrame({
        'stock_code': codes,
        'avg_amount': amounts,
    })


class TestUniverseWithoutTurnoverFilter:

    @patch('strategist.microcap.universe.get_connection')
    def test_no_filter_when_min_turnover_zero(self, mock_conn_factory):
        """min_avg_turnover=0 时不发起成交额查询。"""
        from strategist.microcap.universe import get_daily_universe

        mock_conn = MagicMock()
        mock_conn_factory.return_value = mock_conn

        codes = ['000001.SZ', '000002.SZ', '000003.SZ']
        mvs   = [5e8, 8e8, 12e8]

        with patch('strategist.microcap.universe.pd.read_sql') as mock_sql:
            mock_sql.return_value = _make_basic_df(codes, mvs)
            result = get_daily_universe('2026-01-05', percentile=1.0,
                                        exclude_st=False, require_positive_pe=False,
                                        min_avg_turnover=0)

            # 只有一次 SQL 调用（basic 查询），无成交额查询
            assert mock_sql.call_count == 1
            assert set(result) == set(codes)


class TestUniverseWithTurnoverFilter:

    @patch('strategist.microcap.universe.get_connection')
    def test_low_liquidity_stocks_excluded(self, mock_conn_factory):
        """低于阈值的股票被剔除出股票池。"""
        from strategist.microcap.universe import get_daily_universe

        mock_conn = MagicMock()
        mock_conn_factory.return_value = mock_conn

        codes = ['000001.SZ', '000002.SZ', '000003.SZ']
        mvs   = [5e8, 8e8, 12e8]

        call_count = [0]

        def mock_read_sql(sql, conn, params=None):
            call_count[0] += 1
            if 'pe_ttm' in sql or 'total_mv' in sql:
                return _make_basic_df(codes, mvs)
            # 成交额查询：000001 流动性不足
            return _make_turnover_df(
                ['000002.SZ', '000003.SZ'],
                [6_000_000.0, 8_000_000.0]
            )

        with patch('strategist.microcap.universe.pd.read_sql', side_effect=mock_read_sql):
            result = get_daily_universe(
                '2026-01-05', percentile=1.0,
                exclude_st=False, require_positive_pe=False,
                min_avg_turnover=5_000_000
            )

        assert '000001.SZ' not in result, "低流动性股票应被剔除"
        assert '000002.SZ' in result
        assert '000003.SZ' in result
        assert call_count[0] == 2   # basic + turnover 各一次

    @patch('strategist.microcap.universe.get_connection')
    def test_all_liquid_stocks_kept(self, mock_conn_factory):
        """所有股票均达到流动性阈值时，全部保留。"""
        from strategist.microcap.universe import get_daily_universe

        mock_conn = MagicMock()
        mock_conn_factory.return_value = mock_conn

        codes = ['000001.SZ', '000002.SZ']
        mvs   = [5e8, 8e8]

        def mock_read_sql(sql, conn, params=None):
            if 'pe_ttm' in sql or 'total_mv' in sql:
                return _make_basic_df(codes, mvs)
            return _make_turnover_df(codes, [6_000_000.0, 7_000_000.0])

        with patch('strategist.microcap.universe.pd.read_sql', side_effect=mock_read_sql):
            result = get_daily_universe(
                '2026-01-05', percentile=1.0,
                exclude_st=False, require_positive_pe=False,
                min_avg_turnover=5_000_000
            )

        assert set(result) == set(codes)

    @patch('strategist.microcap.universe.get_connection')
    def test_insufficient_trading_days_excluded(self, mock_conn_factory):
        """近期交易日不足 3 天的股票被剔除（HAVING COUNT >= 3）。"""
        from strategist.microcap.universe import get_daily_universe

        mock_conn = MagicMock()
        mock_conn_factory.return_value = mock_conn

        codes = ['000001.SZ', '000002.SZ']
        mvs   = [5e8, 8e8]

        def mock_read_sql(sql, conn, params=None):
            if 'pe_ttm' in sql or 'total_mv' in sql:
                return _make_basic_df(codes, mvs)
            # 000001 因为 HAVING COUNT < 3 不在结果中
            return _make_turnover_df(['000002.SZ'], [6_000_000.0])

        with patch('strategist.microcap.universe.pd.read_sql', side_effect=mock_read_sql):
            result = get_daily_universe(
                '2026-01-05', percentile=1.0,
                exclude_st=False, require_positive_pe=False,
                min_avg_turnover=5_000_000
            )

        assert '000001.SZ' not in result
        assert '000002.SZ' in result
