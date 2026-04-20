# -*- coding: utf-8 -*-
"""
Unit tests for strategist/backtest/ benchmark enhancement (Phase 4).

Pure-Python tests: no DB, no network.
"""
import pytest
import pandas as pd
import numpy as np
from datetime import date


# ---------------------------------------------------------------------------
# Test BacktestConfig enhancements
# ---------------------------------------------------------------------------

class TestBacktestConfigBenchmark:
    def test_gdp_cpi_defaults(self):
        from strategist.backtest.config import BacktestConfig
        cfg = BacktestConfig()
        assert cfg.gdp_growth_rate == 0.05
        assert cfg.cpi_growth_rate == 0.02
        assert cfg.show_gdp_benchmark is True

    def test_custom_gdp_cpi(self):
        from strategist.backtest.config import BacktestConfig
        cfg = BacktestConfig(gdp_growth_rate=0.06, cpi_growth_rate=0.03)
        assert cfg.gdp_growth_rate == 0.06
        assert cfg.cpi_growth_rate == 0.03


# ---------------------------------------------------------------------------
# Test MetricsCalculator._calculate_reasonability
# ---------------------------------------------------------------------------

class TestReasonability:
    def _get_calculator(self):
        from strategist.backtest.metrics import MetricsCalculator
        return MetricsCalculator()

    def test_overfit_warning(self):
        """Annual return > 3x GDP (15%) => overfit_warning."""
        calc = self._get_calculator()
        gdp_cum, cpi_cum, label = calc._calculate_reasonability(
            annual_return=0.25, years=3.0
        )
        assert label == 'overfit_warning'
        # GDP cumulative for 3 years at 5%
        expected_gdp = (1.05 ** 3) - 1
        assert abs(gdp_cum - expected_gdp) < 1e-6

    def test_underperform_cash(self):
        """Annual return < CPI (2%) => underperform_cash."""
        calc = self._get_calculator()
        gdp_cum, cpi_cum, label = calc._calculate_reasonability(
            annual_return=0.01, years=2.0
        )
        assert label == 'underperform_cash'
        expected_cpi = (1.02 ** 2) - 1
        assert abs(cpi_cum - expected_cpi) < 1e-6

    def test_reasonable(self):
        """Annual return between CPI and 3x GDP => reasonable."""
        calc = self._get_calculator()
        _, _, label = calc._calculate_reasonability(
            annual_return=0.08, years=2.0
        )
        assert label == 'reasonable'

    def test_edge_at_cpi(self):
        """Annual return == CPI => reasonable (not strictly less)."""
        calc = self._get_calculator()
        _, _, label = calc._calculate_reasonability(
            annual_return=0.02, years=1.0
        )
        assert label == 'reasonable'

    def test_edge_at_3x_gdp(self):
        """Annual return == 3x GDP (0.15) => reasonable (not strictly greater)."""
        calc = self._get_calculator()
        _, _, label = calc._calculate_reasonability(
            annual_return=0.15, years=1.0
        )
        assert label == 'reasonable'

    def test_zero_years(self):
        """Zero trading period => empty label."""
        calc = self._get_calculator()
        gdp_cum, cpi_cum, label = calc._calculate_reasonability(
            annual_return=0.10, years=0.0
        )
        assert gdp_cum == 0
        assert cpi_cum == 0
        assert label == ''

    def test_negative_return(self):
        """Negative annual return => underperform_cash."""
        calc = self._get_calculator()
        _, _, label = calc._calculate_reasonability(
            annual_return=-0.05, years=2.0
        )
        assert label == 'underperform_cash'

    def test_custom_rates(self):
        """Custom GDP/CPI rates."""
        calc = self._get_calculator()
        _, _, label = calc._calculate_reasonability(
            annual_return=0.20, years=1.0,
            gdp_rate=0.10, cpi_rate=0.05,
        )
        # 0.20 < 0.10 * 3 = 0.30, and 0.20 > 0.05 => reasonable
        assert label == 'reasonable'


# ---------------------------------------------------------------------------
# Test BacktestResult integration
# ---------------------------------------------------------------------------

class TestBacktestResultFields:
    def test_new_fields_exist(self):
        from strategist.backtest.metrics import BacktestResult
        result = BacktestResult()
        assert hasattr(result, 'gdp_cumulative_return')
        assert hasattr(result, 'cpi_cumulative_return')
        assert hasattr(result, 'reasonability')
        assert result.gdp_cumulative_return == 0
        assert result.cpi_cumulative_return == 0
        assert result.reasonability == ''

    def test_calculate_populates_reasonability(self):
        """Full calculate() should populate GDP/CPI/reasonability fields."""
        from strategist.backtest.metrics import MetricsCalculator

        calc = MetricsCalculator()
        # Build minimal daily_df: 504 trading days (~2 years), 10% total return
        dates = pd.date_range('2024-01-01', periods=504, freq='B')
        values = np.linspace(1_000_000, 1_100_000, 504)
        daily_df = pd.DataFrame({'total_value': values}, index=dates)
        daily_df.index.name = 'date'

        trades_df = pd.DataFrame(columns=['date', 'stock_code', 'action', 'price', 'signal_type'])

        result = calc.calculate(daily_df, trades_df, initial_cash=1_000_000)

        assert result.gdp_cumulative_return > 0
        assert result.cpi_cumulative_return > 0
        assert result.reasonability in ('reasonable', 'overfit_warning', 'underperform_cash')


# ---------------------------------------------------------------------------
# Test Report generation
# ---------------------------------------------------------------------------

class TestReportBenchmarkSection:
    def test_report_contains_benchmark_section(self):
        """Report should contain benchmark comparison when GDP/CPI data present."""
        from strategist.backtest.metrics import BacktestResult
        from strategist.backtest.report import ReportGenerator
        import tempfile
        import os

        result = BacktestResult(
            start_date='2024-01-01',
            end_date='2025-12-31',
            trading_days=504,
            initial_cash=1_000_000,
            final_value=1_100_000,
            total_return=0.10,
            annual_return=0.05,
            max_drawdown=-0.08,
            volatility=0.15,
            sharpe_ratio=1.0,
            sortino_ratio=1.2,
            calmar_ratio=0.625,
            gdp_cumulative_return=0.1025,
            cpi_cumulative_return=0.0404,
            reasonability='reasonable',
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'test_report.md')
            ReportGenerator.generate_markdown_report(result, path, 'Test Strategy')

            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            assert 'Benchmark Comparison' in content
            assert 'GDP' in content
            assert 'CPI' in content
            assert '[OK]' in content
            assert '[OK] **' in content  # reasonability section present

    def test_report_overfit_warning(self):
        """Report should show overfit warning when annual return too high."""
        from strategist.backtest.metrics import BacktestResult
        from strategist.backtest.report import ReportGenerator
        import tempfile
        import os

        result = BacktestResult(
            start_date='2024-01-01',
            end_date='2025-12-31',
            trading_days=504,
            initial_cash=1_000_000,
            final_value=1_500_000,
            total_return=0.50,
            annual_return=0.25,
            max_drawdown=-0.15,
            volatility=0.20,
            sharpe_ratio=1.5,
            sortino_ratio=1.8,
            calmar_ratio=1.67,
            gdp_cumulative_return=0.1025,
            cpi_cumulative_return=0.0404,
            reasonability='overfit_warning',
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'test_report.md')
            ReportGenerator.generate_markdown_report(result, path, 'Test Strategy')

            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            assert '[WARN]' in content
            assert 'GDP' in content  # overfit warning references GDP

    def test_report_no_emoji(self):
        """Verify no emoji characters in report output."""
        from strategist.backtest.metrics import BacktestResult
        from strategist.backtest.report import ReportGenerator
        import tempfile
        import os

        result = BacktestResult(
            start_date='2024-01-01',
            end_date='2025-12-31',
            trading_days=504,
            initial_cash=1_000_000,
            final_value=1_100_000,
            total_return=0.10,
            annual_return=0.05,
            max_drawdown=-0.08,
            volatility=0.15,
            sharpe_ratio=1.0,
            sortino_ratio=1.2,
            calmar_ratio=0.625,
            gdp_cumulative_return=0.1025,
            cpi_cumulative_return=0.0404,
            reasonability='reasonable',
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, 'test_report.md')
            ReportGenerator.generate_markdown_report(result, path, 'Test Strategy')

            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Check no common emoji characters
            for char in content:
                assert ord(char) < 0x1F600 or ord(char) > 0x1F64F, \
                    f"Found emoji character U+{ord(char):04X} in report"
