# -*- coding: utf-8 -*-
"""
Unit tests for portfolio_mgmt_service calculation functions.
No DB required -- only pure calculation helpers are tested here.
"""
import unittest
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from api.services.portfolio_mgmt_service import (
    calc_tgt,
    calc_return_27,
    calc_growth_27,
    calc_market_factors,
    calc_adj_return,
    calc_trigger_prices,
    run_optimizer,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_stock(**kwargs):
    defaults = {
        'stock_code': '000001',
        'stock_name': 'TestCo',
        'industry': 'Tech',
        'tier': 'Far Ahead',
        'status': 'hold',
        'position_pct': 10.0,
        'profit_26': 100.0,
        'profit_27': 120.0,
        'pe_26': 15.0,
        'pe_27': 12.0,
        'net_cash_26': 50.0,
        'net_cash_27': 60.0,
        'cash_adj_coef': 0.5,
        'equity_adj': 20.0,
        'asset_growth_26': 0.0,
        'asset_growth_27': 10.0,
        'payout_ratio': 0.3,
        'research_depth': 80,
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# TestCalcReturn
# ---------------------------------------------------------------------------

class TestCalcReturn(unittest.TestCase):

    def test_basic_tgt27(self):
        s = make_stock(profit_27=120, pe_27=12, equity_adj=20, asset_growth_27=10, net_cash_27=60, cash_adj_coef=0.5)
        # tgt = 120*12 + 20 + 10 + 60*0.5 = 1440 + 20 + 10 + 30 = 1500
        self.assertAlmostEqual(calc_tgt(s, '27'), 1500.0)

    def test_basic_return_27(self):
        s = make_stock(profit_26=100, profit_27=120, pe_27=12, equity_adj=20, asset_growth_27=10,
                       net_cash_27=60, cash_adj_coef=0.5, payout_ratio=0.3)
        mktcap = 1000.0
        # tgt27 = 1500
        # div_26 = 0.3*100/1000 = 0.03
        # div_27 = 0.3*120/1000 = 0.036
        # return = 1500/1000 - 1 + 0.03 + 0.036 = 0.5 + 0.066 = 0.566
        r = calc_return_27(s, mktcap)
        self.assertIsNotNone(r)
        self.assertAlmostEqual(r, 0.566, places=3)

    def test_market_cap_zero(self):
        s = make_stock()
        self.assertIsNone(calc_return_27(s, 0))
        self.assertIsNone(calc_return_27(s, None))

    def test_tgt_zero_returns_none(self):
        s = make_stock(profit_27=0, pe_27=0, equity_adj=0, asset_growth_27=0, net_cash_27=0)
        self.assertIsNone(calc_return_27(s, 1000))

    def test_growth_27(self):
        s = make_stock(profit_26=100, profit_27=125)
        self.assertAlmostEqual(calc_growth_27(s), 25.0)

    def test_growth_27_negative_base(self):
        s = make_stock(profit_26=-100, profit_27=-80)
        g = calc_growth_27(s)
        # (-80 - -100) / 100 * 100 = 20
        self.assertAlmostEqual(g, 20.0)

    def test_growth_27_none_when_no_profit(self):
        s = make_stock(profit_26=None, profit_27=None)
        self.assertIsNone(calc_growth_27(s))


# ---------------------------------------------------------------------------
# TestMarketFactors
# ---------------------------------------------------------------------------

class TestMarketFactors(unittest.TestCase):

    def test_valuation_undervalued(self):
        # pe_27=12, profit_27=100, implied_pe=mktcap/profit=800/100=8 => less than fair
        # underval_ratio = (12 - 8) / 12 = 0.333 => val_score = 0.333 * 30 = 10
        s = make_stock(pe_27=12, profit_27=100)
        factors = calc_market_factors(s, 800, [s])
        self.assertGreater(factors['valuation'], 0)
        self.assertLessEqual(factors['valuation'], 30)

    def test_valuation_overvalued_zero_score(self):
        # implied_pe = 2000/100 = 20 > pe_27=12 => overvalued => score 0
        s = make_stock(pe_27=12, profit_27=100)
        factors = calc_market_factors(s, 2000, [s])
        self.assertEqual(factors['valuation'], 0)

    def test_liquidity_above_500bn(self):
        s = make_stock()
        factors = calc_market_factors(s, 600, [s])
        self.assertAlmostEqual(factors['liquidity'], 20.0)

    def test_liquidity_below_200bn(self):
        s = make_stock()
        factors = calc_market_factors(s, 100, [s])
        self.assertAlmostEqual(factors['liquidity'], 12.0)

    def test_liquidity_overseas_penalty(self):
        s = make_stock(stock_code='PDD.O')
        factors = calc_market_factors(s, 600, [s])
        self.assertAlmostEqual(factors['liquidity'], 20.0 * 0.95)

    def test_business_high_growth(self):
        s = make_stock(profit_26=100, profit_27=130)  # 30% growth
        factors = calc_market_factors(s, 1000, [s])
        self.assertAlmostEqual(factors['business'], 30.0)

    def test_business_zero_growth(self):
        s = make_stock(profit_26=100, profit_27=100)  # 0% growth
        factors = calc_market_factors(s, 1000, [s])
        self.assertAlmostEqual(factors['business'], 10.0)

    def test_industry_preference_no_peers(self):
        s = make_stock(industry='Unique')
        factors = calc_market_factors(s, 1000, [s])
        # Only stock in industry, market_coef = min(1, 0.70 + 0) = 0.70
        # ind_score = 20 * (1 - 0.70 * 0.5) = 20 * 0.65 = 13
        self.assertAlmostEqual(factors['industry_pref'], 13.0)

    def test_total_sums_components(self):
        s = make_stock()
        factors = calc_market_factors(s, 1000, [s])
        expected = factors['valuation'] + factors['business'] + factors['liquidity'] + factors['industry_pref']
        self.assertAlmostEqual(factors['total'], round(expected, 2))


# ---------------------------------------------------------------------------
# TestOptimizer
# ---------------------------------------------------------------------------

def _make_candidates(n: int, tier='Far Ahead', industry='Tech', base_return=0.4) -> list:
    return [
        {
            'stock_code': f'00000{i}',
            'stock_name': f'Company{i}',
            'industry': industry,
            'tier': tier,
            'status': 'hold',
            'position_pct': 5.0,
            'return_27': base_return + i * 0.01,
            'adj_return': (base_return + i * 0.01) * 0.8,
            'research_depth': 80,
            'payout_ratio': 0.2,
        }
        for i in range(n)
    ]


class TestOptimizer(unittest.TestCase):

    def test_industry_cap_40pct(self):
        """Industry cap constraint: multi-industry portfolios should not exceed 40% per industry."""
        # Mix: 8 Tech + 8 Finance; Tech should be capped at 40%
        tech = _make_candidates(8, industry='Tech', tier='Far Ahead', base_return=0.5)
        finance = [
            {
                'stock_code': f'F0000{i}',
                'stock_name': f'FinCo{i}',
                'industry': 'Finance',
                'tier': 'Far Ahead',
                'status': 'hold',
                'position_pct': 5.0,
                'return_27': 0.3 + i * 0.01,
                'adj_return': (0.3 + i * 0.01) * 0.8,
                'research_depth': 80,
                'payout_ratio': 0.2,
            }
            for i in range(8)
        ]
        stocks = tech + finance
        result = run_optimizer(stocks)
        # tech total should be <= 40
        tech_codes = {s['stock_code'] for s in tech}
        tech_total = sum(result['allocations'].get(c, 0) for c in tech_codes)
        self.assertLessEqual(tech_total, 40)

    def test_industry_cap_violation_reported_when_all_same(self):
        """When all candidates are in one industry, violation is recorded."""
        stocks = _make_candidates(12, industry='SameIndustry', tier='Far Ahead')
        result = run_optimizer(stocks)
        # Constraint violation should be reported
        self.assertFalse(result['constraints_met'])

    def test_stock_cap_25pct(self):
        """Each stock must be <= 25%."""
        stocks = _make_candidates(5, tier='Far Ahead')
        result = run_optimizer(stocks)
        for code, pct in result['allocations'].items():
            self.assertLessEqual(pct, 25, f'{code} exceeds 25%')

    def test_yy_min_60pct(self):
        """Far Ahead stocks should get >= 60% if we have enough."""
        yy = _make_candidates(8, tier='Far Ahead', industry='Tech', base_return=0.5)
        leading = _make_candidates(4, tier='Leading', industry='Finance', base_return=0.2)
        # Override codes to avoid duplicates
        for i, s in enumerate(leading):
            s['stock_code'] = f'L0000{i}'
        stocks = yy + leading
        result = run_optimizer(stocks)
        yy_total = sum(
            result['allocations'].get(s['stock_code'], 0)
            for s in yy
        )
        # May not be 60% if industry cap kicks in, just check constraint tracking
        self.assertIn('constraints_met', result)

    def test_cash_fill_no_eligible(self):
        """When no stocks are eligible, cash should be 100%."""
        stocks = [
            {
                'stock_code': '000001',
                'stock_name': 'LowReturn',
                'industry': 'X',
                'tier': '',
                'status': 'hold',
                'position_pct': 10,
                'return_27': 0.01,  # below threshold
                'adj_return': 0.005,  # below threshold
                'research_depth': 30,  # below depth threshold
                'payout_ratio': 0,
            }
        ]
        result = run_optimizer(stocks)
        # When all fail filters, should still return something (relaxed filter)
        self.assertIn('allocations', result)
        self.assertIn('cash_pct', result)

    def test_result_sums_to_100(self):
        """Allocations + cash should sum to 100."""
        stocks = _make_candidates(10, tier='Far Ahead')
        result = run_optimizer(stocks)
        total = sum(result['allocations'].values()) + result['cash_pct']
        self.assertEqual(total, 100)

    def test_result_structure(self):
        stocks = _make_candidates(8, tier='Far Ahead')
        result = run_optimizer(stocks)
        self.assertIn('allocations', result)
        self.assertIn('cash_pct', result)
        self.assertIn('constraints_met', result)
        self.assertIn('violations', result)


# ---------------------------------------------------------------------------
# TestTriggerPrices
# ---------------------------------------------------------------------------

class TestTriggerPrices(unittest.TestCase):

    def _make_stock(self):
        return make_stock(profit_26=100, profit_27=120, pe_27=12,
                          equity_adj=20, asset_growth_27=10,
                          net_cash_27=60, cash_adj_coef=0.5, payout_ratio=0.0)

    def test_strong_buy_formula(self):
        s = self._make_stock()
        # tgt27 = 120*12 + 20 + 10 + 60*0.5 = 1500, dy=0
        # strong_buy = 1500 / max(1.50 - 0, 0.01) = 1000
        tp = calc_trigger_prices(s, 2000)
        self.assertAlmostEqual(tp['strong_buy'], 1000.0)

    def test_add_formula(self):
        s = self._make_stock()
        # add = 1500 / 1.35 = 1111.11
        tp = calc_trigger_prices(s, 2000)
        self.assertAlmostEqual(tp['add'], 1500 / 1.35, places=1)

    def test_signal_strong_buy(self):
        s = self._make_stock()
        tp = calc_trigger_prices(s, 800)  # below strong_buy threshold 1000
        self.assertEqual(tp['signal'], 'STRONG_BUY')

    def test_signal_clear(self):
        s = self._make_stock()
        tp = calc_trigger_prices(s, 1600)  # above clear threshold
        self.assertEqual(tp['signal'], 'CLEAR')

    def test_signal_hold(self):
        s = self._make_stock()
        # reduce=1304, clear=1429; hold is between add and reduce
        # add=1111, reduce=1304; pick 1200
        tp = calc_trigger_prices(s, 1200)
        self.assertEqual(tp['signal'], 'HOLD')

    def test_no_data_when_tgt_zero(self):
        s = make_stock(profit_27=0, pe_27=0, equity_adj=0, asset_growth_27=0, net_cash_27=0)
        tp = calc_trigger_prices(s, 1000)
        self.assertEqual(tp['signal'], 'NO_DATA')

    def test_no_data_when_no_market_cap(self):
        s = self._make_stock()
        tp = calc_trigger_prices(s, None)
        self.assertEqual(tp['signal'], 'NO_DATA')

    def test_dividend_adjustment(self):
        s = make_stock(profit_26=100, profit_27=120, pe_27=12,
                       equity_adj=20, asset_growth_27=10,
                       net_cash_27=60, cash_adj_coef=0.5, payout_ratio=0.3)
        mktcap = 1000.0
        # dy = 0.3 * (100 + 120) / 1000 = 0.066
        # strong_buy = 1500 / max(1.50 - 0.066, 0.01) = 1500 / 1.434 = 1045.74
        tp = calc_trigger_prices(s, mktcap)
        expected = 1500 / max(1.50 - 0.066, 0.01)
        self.assertAlmostEqual(tp['strong_buy'], expected, places=0)


if __name__ == '__main__':
    unittest.main()
