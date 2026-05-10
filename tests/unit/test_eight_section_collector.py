# -*- coding: utf-8 -*-
"""
Unit tests for EightSectionDataCollector.

Tests the core calculation logic (Beta, FCF, support/resistance)
without requiring database connections.
"""
import pytest
from unittest.mock import patch, MagicMock
from investment_rag.report_engine.eight_section.data_collector import (
    EightSectionDataCollector,
    _sf,
    _pct,
    _yuan,
    _num,
)


class TestHelperFunctions:
    """Test utility functions."""

    def test_sf_none(self):
        assert _sf(None) is None

    def test_sf_decimal(self):
        from decimal import Decimal
        assert _sf(Decimal("123.45")) == 123.45

    def test_sf_nan(self):
        assert _sf(float("nan")) is None

    def test_sf_string(self):
        assert _sf("abc") is None

    def test_pct_none(self):
        assert _pct(None) == "(数据缺失)"

    def test_pct_value(self):
        assert _pct(12.345) == "12.35%"

    def test_pct_digits(self):
        assert _pct(12.345, 1) == "12.3%"

    def test_yuan_value(self):
        assert _yuan(123.456) == "123.46亿"

    def test_yuan_none(self):
        assert _yuan(None) == "(数据缺失)"

    def test_num_value(self):
        assert _num(123.456) == "123.46"

    def test_num_none(self):
        assert _num(None) == "(数据缺失)"


class TestCalculateBeta:
    """Test dynamic Beta calculation based on industry."""

    def _make_collector(self, sw_level1="", sw_level2=""):
        """Create a collector with mocked DB query for industry lookup."""
        collector = EightSectionDataCollector.__new__(EightSectionDataCollector)
        collector._eq = MagicMock()
        collector._env = "online"
        collector._q = MagicMock(return_value=[
            {"sw_level1": sw_level1, "sw_level2": sw_level2}
        ])
        return collector

    def test_cyclical_industry(self):
        """Cyclical industries (metals, mining) should get Beta 1.1."""
        for industry in ["有色金属", "采掘", "钢铁", "化工"]:
            c = self._make_collector(sw_level1=industry)
            beta = c._calculate_beta("000933", "000933.SZ")
            assert beta == 1.1, f"Expected 1.1 for {industry}, got {beta}"

    def test_tech_industry(self):
        """Tech/growth industries should get Beta 1.3."""
        for industry in ["电子", "计算机", "通信"]:
            c = self._make_collector(sw_level1=industry)
            beta = c._calculate_beta("688012", "688012.SH")
            assert beta == 1.3, f"Expected 1.3 for {industry}, got {beta}"

    def test_defensive_industry(self):
        """Defensive industries should get lower Beta."""
        c = self._make_collector(sw_level1="食品饮料")
        beta = c._calculate_beta("600519", "600519.SH")
        assert beta == 0.9

    def test_bank_beta(self):
        """Banks should get lowest Beta."""
        c = self._make_collector(sw_level1="银行")
        beta = c._calculate_beta("601398", "601398.SH")
        assert beta == 0.8

    def test_default_beta(self):
        """Unmatched industry should default to 1.1."""
        c = self._make_collector(sw_level1="未知行业")
        beta = c._calculate_beta("000001", "000001.SZ")
        assert beta == 1.1

    def test_no_industry_data(self):
        """Missing industry data should default to 1.1."""
        collector = EightSectionDataCollector.__new__(EightSectionDataCollector)
        collector._q = MagicMock(return_value=[])
        beta = collector._calculate_beta("000001", "000001.SZ")
        assert beta == 1.1

    def test_beta_reason_set(self):
        """Beta reason should be set for LLM context."""
        c = self._make_collector(sw_level1="电子")
        c._calculate_beta("688012", "688012.SH")
        assert "电子" in c._beta_reason


class TestCalculateBaseFCF:
    """Test FCF calculation from cashflow data."""

    def _make_collector(self, ocf=None, icf=None, net_profit=None):
        """Create collector with mocked cashflow and financial data."""
        collector = EightSectionDataCollector.__new__(EightSectionDataCollector)
        collector._q = MagicMock()

        cf_row = []
        if ocf is not None:
            cf_row.append({"operating_cashflow": ocf, "investing_cashflow": icf})
        collector._q.side_effect = [
            cf_row,  # cashflow query
        ]
        return collector

    def test_fcf_from_cashflow(self):
        """FCF should be OCF - |capex| when capex is negative."""
        c = self._make_collector(ocf=87.43, icf=-12.93)
        annual = [{"net_profit": 40.05}]
        fcf, source = c._calculate_base_fcf("000933", annual)
        # OCF 87.43 - |ICF| 12.93 = 74.50
        assert fcf == pytest.approx(74.50, abs=0.01)
        assert "OCF" in source

    def test_fcf_heavy_capex(self):
        """Heavy capex company: OCF < capex, should use OCF * 0.5."""
        c = self._make_collector(ocf=297.92, icf=-309.25)
        annual = [{"net_profit": 178.84}]
        fcf, source = c._calculate_base_fcf("000933", annual)
        # capex > OCF, use sustainable FCF = OCF * 0.5
        assert fcf == pytest.approx(148.96, abs=0.01)
        assert "重资本开支" in source

    def test_fcf_no_investing(self):
        """When investing is positive (unusual), capex=0, FCF=OCF."""
        c = self._make_collector(ocf=50.0, icf=5.0)
        annual = [{"net_profit": 30.0}]
        fcf, source = c._calculate_base_fcf("000933", annual)
        assert fcf == 50.0

    def test_fcf_fallback_to_net_profit(self):
        """When cashflow data is missing, fallback to 0.7x net profit."""
        collector = EightSectionDataCollector.__new__(EightSectionDataCollector)
        collector._q = MagicMock(return_value=[])
        annual = [{"net_profit": 40.05}]
        fcf, source = collector._calculate_base_fcf("000933", annual)
        assert fcf == pytest.approx(28.035, abs=0.01)
        assert "估算" in source

    def test_fcf_no_data(self):
        """When all data is missing, return None."""
        collector = EightSectionDataCollector.__new__(EightSectionDataCollector)
        collector._q = MagicMock(return_value=[])
        fcf, source = collector._calculate_base_fcf("000933", [])
        assert fcf is None


class TestSupportResistance:
    """Test support and resistance level calculation in Ch7."""

    def _make_generator(self):
        from investment_rag.report_engine.eight_section.section_generator import (
            EightSectionGenerator,
        )
        gen = EightSectionGenerator.__new__(EightSectionGenerator)
        return gen

    def test_support_resistance_parsing(self):
        """Should extract Bollinger band and MA levels as support/resistance."""
        gen = self._make_generator()
        data = {
            "daily_quotes": "**20日涨幅**: -3.1%",
            "technical_factors": (
                "收盘价: 31.00\n"
                "MA5/MA10/MA20: 32.12 / 32.38 / 33.27\n"
                "MA60/MA120/MA250: 32.73 / 30.24 / 24.24\n"
                "布林带: 上轨=35.55, 中轨=33.27, 下轨=30.99"
            ),
        }
        signal = gen._summarize_technical_signal(data)
        assert "支撑" in signal
        assert "阻力" in signal
        assert "布林带下轨" in signal
        assert "MA20" in signal

    def test_no_bollinger_data(self):
        """When no Bollinger data, should not crash."""
        gen = self._make_generator()
        data = {
            "daily_quotes": "",
            "technical_factors": "收盘价: 31.00",
        }
        signal = gen._summarize_technical_signal(data)
        assert "支撑" not in signal
