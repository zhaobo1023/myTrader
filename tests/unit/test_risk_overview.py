# -*- coding: utf-8 -*-
"""
Unit tests for api/routers/risk.py -- _do_overview function.

Tests are pure-Python: no DB, no FastAPI, no network.
All database calls are mocked via unittest.mock.patch.

Run:
    cd /Users/wenwen/data0/person/myTrader
    python -m pytest tests/unit/test_risk_overview.py -v
"""
import sys
import os
import types
import importlib
from unittest.mock import patch, MagicMock, call
from decimal import Decimal

import pytest

# ---------------------------------------------------------------------------
# We need to import _do_overview without triggering FastAPI / DB / heavy deps.
# Strategy: extract the logic into a callable by loading only the inner
# function. We do this by importing the router module with heavy dependencies
# stubbed out, then calling the closure directly.
# ---------------------------------------------------------------------------

# Stub out modules that would fail to import in a pure unit-test environment.
_STUB_MODULES = [
    'api.middleware.auth',
    'api.models.user',
    'data_analyst.risk_assessment.storage',
    'fastapi',
]

for _mod_name in _STUB_MODULES:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

# Make sure fastapi.APIRouter / Depends / HTTPException are mock-able
import fastapi  # noqa: E402  (already mocked above)
fastapi.APIRouter = MagicMock(return_value=MagicMock())
fastapi.Depends = MagicMock()
fastapi.HTTPException = Exception  # simplest stand-in

# ---------------------------------------------------------------------------
# Extract _do_overview by parsing it out of the risk router source.
# We use exec() with a minimal namespace so we avoid touching the DB.
# ---------------------------------------------------------------------------

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RISK_ROUTER_PATH = os.path.join(ROOT, 'api', 'routers', 'risk.py')



def _build_do_overview_with_logger():
    """Like _build_do_overview but injects a mock logger into the namespace."""
    with open(RISK_ROUTER_PATH, encoding='utf-8') as fh:
        source = fh.read()

    lines = source.splitlines()
    start = None
    end = None
    for i, line in enumerate(lines):
        if line.strip().startswith('def _do_overview('):
            start = i
        if start is not None and i > start:
            if line.startswith('    try:') and i > start + 5:
                end = i
                break

    func_lines = lines[start:end]
    dedented = '\n'.join(l[4:] if l.startswith('    ') else l for l in func_lines)

    import logging
    ns: dict = {'logger': logging.getLogger('test_risk_overview')}
    exec(compile(dedented, RISK_ROUTER_PATH, 'exec'), ns)  # noqa: S102
    return ns['_do_overview']


_do_overview = _build_do_overview_with_logger()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_svd_row(state='板块分化', is_mutation=False, top1=0.32, top3=0.58):
    return [{'calc_date': '2026-04-18', 'market_state': state,
              'is_mutation': is_mutation, 'top1_var_ratio': top1,
              'top3_var_ratio': top3}]


def _make_qvix_row(value: float):
    return [{'date': '2026-04-18', 'value': value}]


def _make_pos_rows(*items):
    """
    items: list of (stock_code, stock_name, shares, cost_price)
    """
    return [
        {'stock_code': c, 'stock_name': n, 'shares': s, 'cost_price': cp}
        for c, n, s, cp in items
    ]


def _make_ind_rows(mapping: dict):
    """mapping: {stock_code: sw_level1}"""
    return [{'stock_code': c, 'sw_level1': ind, 'industry': ind}
            for c, ind in mapping.items()]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

USER_ID = 42


class TestNormalData:
    """Scenario 1: SVD has data, QVIX has data, positions exist -> full overview."""

    def test_returns_all_four_keys(self):
        pos_rows = _make_pos_rows(
            ('000858.SZ', '五粮液', 1000, 150.0),
            ('600519.SH', '贵州茅台', 100, 1800.0),
        )
        ind_rows = _make_ind_rows({'000858.SZ': '食品饮料', '600519.SH': '食品饮料'})

        def fake_execute(sql, params=None, env=None):
            if 'trade_svd_market_state' in sql:
                return _make_svd_row()
            if 'macro_data' in sql:
                return _make_qvix_row(18.5)
            if 'user_positions' in sql:
                return pos_rows
            if 'trade_stock_basic' in sql:
                return ind_rows
            return []

        with patch('config.db.execute_query', side_effect=fake_execute):
            result = _do_overview(USER_ID)

        assert result['svd'] is not None
        assert result['qvix'] is not None
        assert result['concentration'] is not None
        assert result['sector'] is not None

    def test_svd_fields_populated(self):
        pos_rows = _make_pos_rows(('000858.SZ', '五粮液', 1000, 150.0))
        ind_rows = _make_ind_rows({'000858.SZ': '食品饮料'})

        def fake_execute(sql, params=None, env=None):
            if 'trade_svd_market_state' in sql:
                return _make_svd_row('个股行情', False, 0.25, 0.55)
            if 'macro_data' in sql:
                return _make_qvix_row(12.0)
            if 'user_positions' in sql:
                return pos_rows
            if 'trade_stock_basic' in sql:
                return ind_rows
            return []

        with patch('config.db.execute_query', side_effect=fake_execute):
            result = _do_overview(USER_ID)

        svd = result['svd']
        assert svd['state'] == '个股行情'
        assert svd['is_mutation'] is False
        assert svd['top1_ratio'] == round(0.25, 4)
        assert svd['top3_ratio'] == round(0.55, 4)
        assert svd['date'] == '2026-04-18'


class TestSvdNoData:
    """Scenario 2: SVD table returns empty -> svd field is None, no exception."""

    def test_svd_none_when_empty(self):
        pos_rows = _make_pos_rows(('000858.SZ', '五粮液', 1000, 150.0))
        ind_rows = _make_ind_rows({'000858.SZ': '食品饮料'})

        def fake_execute(sql, params=None, env=None):
            if 'trade_svd_market_state' in sql:
                return []   # empty
            if 'macro_data' in sql:
                return _make_qvix_row(20.0)
            if 'user_positions' in sql:
                return pos_rows
            if 'trade_stock_basic' in sql:
                return ind_rows
            return []

        with patch('config.db.execute_query', side_effect=fake_execute):
            result = _do_overview(USER_ID)

        assert result['svd'] is None
        # other sections should still work
        assert result['qvix'] is not None

    def test_svd_none_when_db_raises(self):
        """DB exception on SVD query -> svd is None, rest unaffected."""
        pos_rows = _make_pos_rows(('000858.SZ', '五粮液', 1000, 150.0))
        ind_rows = _make_ind_rows({'000858.SZ': '食品饮料'})

        def fake_execute(sql, params=None, env=None):
            if 'trade_svd_market_state' in sql:
                raise RuntimeError('table not found')
            if 'macro_data' in sql:
                return _make_qvix_row(14.0)
            if 'user_positions' in sql:
                return pos_rows
            if 'trade_stock_basic' in sql:
                return ind_rows
            return []

        with patch('config.db.execute_query', side_effect=fake_execute):
            result = _do_overview(USER_ID)

        assert result['svd'] is None
        assert result['qvix'] is not None


class TestQvixLevels:
    """Scenario 3: QVIX boundary value tests."""

    def _run_with_qvix(self, value: float) -> dict:
        pos_rows = _make_pos_rows(('000858.SZ', '五粮液', 1000, 150.0))
        ind_rows = _make_ind_rows({'000858.SZ': '食品饮料'})

        def fake_execute(sql, params=None, env=None):
            if 'trade_svd_market_state' in sql:
                return _make_svd_row()
            if 'macro_data' in sql:
                return _make_qvix_row(value)
            if 'user_positions' in sql:
                return pos_rows
            if 'trade_stock_basic' in sql:
                return ind_rows
            return []

        with patch('config.db.execute_query', side_effect=fake_execute):
            result = _do_overview(USER_ID)
        return result['qvix']

    def test_qvix_below_15_is_low(self):
        q = self._run_with_qvix(14.9)
        assert q['level'] == 'low'
        assert q['label'] == '平稳'
        assert q['suggested_exposure'] == 1.0

    def test_qvix_exactly_15_is_medium(self):
        q = self._run_with_qvix(15.0)
        assert q['level'] == 'medium'
        assert q['label'] == '焦虑'
        assert q['suggested_exposure'] == 0.77

    def test_qvix_19_is_medium(self):
        q = self._run_with_qvix(19.9)
        assert q['level'] == 'medium'
        assert q['suggested_exposure'] == 0.77

    def test_qvix_exactly_20_is_high(self):
        q = self._run_with_qvix(20.0)
        assert q['level'] == 'high'
        assert q['label'] == '恐慌'
        assert q['suggested_exposure'] == 0.47

    def test_qvix_29_is_high(self):
        q = self._run_with_qvix(29.9)
        assert q['level'] == 'high'

    def test_qvix_exactly_30_is_critical(self):
        q = self._run_with_qvix(30.0)
        assert q['level'] == 'critical'
        assert q['label'] == '极度恐慌'
        assert q['suggested_exposure'] == 0.15

    def test_qvix_39_is_critical(self):
        q = self._run_with_qvix(39.9)
        assert q['level'] == 'critical'
        assert q['suggested_exposure'] == 0.15

    def test_qvix_exactly_40_is_doomsday(self):
        q = self._run_with_qvix(40.0)
        assert q['level'] == 'critical'
        assert q['label'] == '末日级别'
        assert q['suggested_exposure'] == 0.0

    def test_qvix_value_stored_correctly(self):
        q = self._run_with_qvix(25.3)
        assert q['value'] == 25.3


class TestNoPositions:
    """Scenario 4: No position data -> concentration and sector are None."""

    def test_no_positions_returns_none_concentration_and_sector(self):
        def fake_execute(sql, params=None, env=None):
            if 'trade_svd_market_state' in sql:
                return _make_svd_row()
            if 'macro_data' in sql:
                return _make_qvix_row(18.0)
            if 'user_positions' in sql:
                return []   # empty
            return []

        with patch('config.db.execute_query', side_effect=fake_execute):
            result = _do_overview(USER_ID)

        assert result['concentration'] is None
        assert result['sector'] is None

    def test_positions_with_zero_shares_treated_as_empty(self):
        """Positions where shares or cost_price is falsy are filtered out."""
        pos_rows = [
            {'stock_code': '000858.SZ', 'stock_name': '五粮液', 'shares': 0, 'cost_price': 150.0},
            {'stock_code': '600519.SH', 'stock_name': '贵州茅台', 'shares': None, 'cost_price': 1800.0},
        ]

        def fake_execute(sql, params=None, env=None):
            if 'trade_svd_market_state' in sql:
                return _make_svd_row()
            if 'macro_data' in sql:
                return _make_qvix_row(18.0)
            if 'user_positions' in sql:
                return pos_rows
            return []

        with patch('config.db.execute_query', side_effect=fake_execute):
            result = _do_overview(USER_ID)

        # All rows filtered by the list comprehension (requires truthy shares and cost_price)
        assert result['concentration'] is None
        assert result['sector'] is None


class TestOverweightSingleStock:
    """Scenario 5: Single stock exceeds 25% threshold."""

    def test_overweight_stock_detected(self):
        # 000858: 9000 * 10 = 90_000; 600519: 1 * 1000 = 1000 total=91000
        # 000858 weight = 90000/91000 ~ 98.9% >> 25%
        pos_rows = _make_pos_rows(
            ('000858.SZ', '五粮液', 9000, 10.0),
            ('600519.SH', '贵州茅台', 1, 1000.0),
        )
        ind_rows = _make_ind_rows({'000858.SZ': '食品饮料', '600519.SH': '食品饮料'})

        def fake_execute(sql, params=None, env=None):
            if 'trade_svd_market_state' in sql:
                return _make_svd_row()
            if 'macro_data' in sql:
                return _make_qvix_row(15.0)
            if 'user_positions' in sql:
                return pos_rows
            if 'trade_stock_basic' in sql:
                return ind_rows
            return []

        with patch('config.db.execute_query', side_effect=fake_execute):
            result = _do_overview(USER_ID)

        overweight = result['concentration']['overweight_stocks']
        codes = [s['stock_code'] for s in overweight]
        assert '000858.SZ' in codes, 'Expected 000858 to be flagged as overweight'

    def test_no_overweight_when_evenly_distributed(self):
        # Four equal positions: each 25% -> not strictly > 25
        pos_rows = _make_pos_rows(
            ('000001.SZ', 'A', 100, 100.0),
            ('000002.SZ', 'B', 100, 100.0),
            ('000003.SZ', 'C', 100, 100.0),
            ('000004.SZ', 'D', 100, 100.0),
        )
        ind_rows = _make_ind_rows({
            '000001.SZ': '银行', '000002.SZ': '银行',
            '000003.SZ': '地产', '000004.SZ': '地产',
        })

        def fake_execute(sql, params=None, env=None):
            if 'trade_svd_market_state' in sql:
                return _make_svd_row()
            if 'macro_data' in sql:
                return _make_qvix_row(15.0)
            if 'user_positions' in sql:
                return pos_rows
            if 'trade_stock_basic' in sql:
                return ind_rows
            return []

        with patch('config.db.execute_query', side_effect=fake_execute):
            result = _do_overview(USER_ID)

        # weight = 25.0, threshold is strictly > 25
        assert result['concentration']['overweight_stocks'] == []

    def test_max_stock_is_largest_weight(self):
        pos_rows = _make_pos_rows(
            ('000858.SZ', '五粮液', 3000, 100.0),    # val = 300_000
            ('600519.SH', '贵州茅台', 100, 500.0),    # val =  50_000
        )
        ind_rows = _make_ind_rows({'000858.SZ': '食品饮料', '600519.SH': '食品饮料'})

        def fake_execute(sql, params=None, env=None):
            if 'trade_svd_market_state' in sql:
                return _make_svd_row()
            if 'macro_data' in sql:
                return _make_qvix_row(15.0)
            if 'user_positions' in sql:
                return pos_rows
            if 'trade_stock_basic' in sql:
                return ind_rows
            return []

        with patch('config.db.execute_query', side_effect=fake_execute):
            result = _do_overview(USER_ID)

        max_stock = result['concentration']['max_stock']
        assert max_stock['stock_code'] == '000858.SZ'
        # 300_000 / 350_000 = 85.7%
        assert max_stock['weight'] > 80.0


class TestOverweightSector:
    """Scenario 6: Sector concentration exceeds 40% threshold."""

    def test_overweight_sector_detected(self):
        # 食品饮料: 000858(val=900k) + 600519(val=100k) = 1_000_000
        # 银行: 000001(val=1000) => total ~ 1_001_000
        # 食品饮料 weight ~ 99.9% > 40
        pos_rows = _make_pos_rows(
            ('000858.SZ', '五粮液', 9000, 100.0),
            ('600519.SH', '贵州茅台', 100, 1000.0),
            ('000001.SZ', '平安银行', 10, 10.0),
        )
        ind_rows = _make_ind_rows({
            '000858.SZ': '食品饮料',
            '600519.SH': '食品饮料',
            '000001.SZ': '银行',
        })

        def fake_execute(sql, params=None, env=None):
            if 'trade_svd_market_state' in sql:
                return _make_svd_row()
            if 'macro_data' in sql:
                return _make_qvix_row(15.0)
            if 'user_positions' in sql:
                return pos_rows
            if 'trade_stock_basic' in sql:
                return ind_rows
            return []

        with patch('config.db.execute_query', side_effect=fake_execute):
            result = _do_overview(USER_ID)

        overweight_sectors = result['sector']['overweight_sectors']
        industries = [s['industry'] for s in overweight_sectors]
        assert '食品饮料' in industries

    def test_sector_with_unknown_industry_excluded_from_weights(self):
        """Stocks with unknown industry should not appear in sector_weights."""
        pos_rows = _make_pos_rows(
            ('000858.SZ', '五粮液', 1000, 100.0),
            ('999999.SZ', '未知股', 1000, 100.0),
        )
        # Only 000858 is in trade_stock_basic; 999999 maps to '未知'
        ind_rows = [{'stock_code': '000858.SZ', 'sw_level1': '食品饮料', 'industry': '食品饮料'}]

        def fake_execute(sql, params=None, env=None):
            if 'trade_svd_market_state' in sql:
                return _make_svd_row()
            if 'macro_data' in sql:
                return _make_qvix_row(15.0)
            if 'user_positions' in sql:
                return pos_rows
            if 'trade_stock_basic' in sql:
                return ind_rows
            return []

        with patch('config.db.execute_query', side_effect=fake_execute):
            result = _do_overview(USER_ID)

        sector = result['sector']
        industries_in_weights = [s['industry'] for s in sector['sector_weights']]
        assert '未知' not in industries_in_weights
        # unknown_pct should reflect the 50% value
        assert sector['unknown_pct'] == 50.0

    def test_no_overweight_sector_when_well_diversified(self):
        # Three sectors, each ~33%
        pos_rows = _make_pos_rows(
            ('000858.SZ', '五粮液', 100, 100.0),
            ('000001.SZ', '平安银行', 100, 100.0),
            ('601318.SH', '中国平安', 100, 100.0),
        )
        ind_rows = _make_ind_rows({
            '000858.SZ': '食品饮料',
            '000001.SZ': '银行',
            '601318.SH': '保险',
        })

        def fake_execute(sql, params=None, env=None):
            if 'trade_svd_market_state' in sql:
                return _make_svd_row()
            if 'macro_data' in sql:
                return _make_qvix_row(15.0)
            if 'user_positions' in sql:
                return pos_rows
            if 'trade_stock_basic' in sql:
                return ind_rows
            return []

        with patch('config.db.execute_query', side_effect=fake_execute):
            result = _do_overview(USER_ID)

        assert result['sector']['overweight_sectors'] == []


class TestEdgeCases:
    """Additional edge-case coverage."""

    def test_decimal_values_from_db_are_handled(self):
        """DB may return Decimal types; ensure float() conversion works."""
        svd_row = [{'calc_date': '2026-04-18', 'market_state': '板块分化',
                     'is_mutation': 0, 'top1_var_ratio': Decimal('0.3200'),
                     'top3_var_ratio': Decimal('0.5800')}]
        qvix_row = [{'date': '2026-04-18', 'value': Decimal('22.50')}]
        pos_rows = _make_pos_rows(('000858.SZ', '五粮液', 1000, Decimal('150.00')))
        ind_rows = _make_ind_rows({'000858.SZ': '食品饮料'})

        def fake_execute(sql, params=None, env=None):
            if 'trade_svd_market_state' in sql:
                return svd_row
            if 'macro_data' in sql:
                return qvix_row
            if 'user_positions' in sql:
                return pos_rows
            if 'trade_stock_basic' in sql:
                return ind_rows
            return []

        with patch('config.db.execute_query', side_effect=fake_execute):
            result = _do_overview(USER_ID)

        # Should not raise; qvix value should be float
        assert isinstance(result['qvix']['value'], float)
        assert result['qvix']['value'] == 22.5

    def test_mutation_flag_false_when_db_returns_zero(self):
        """is_mutation=0 (integer) should map to bool False."""
        svd_row = [{'calc_date': '2026-04-18', 'market_state': '个股行情',
                     'is_mutation': 0, 'top1_var_ratio': 0.25, 'top3_var_ratio': 0.55}]

        def fake_execute(sql, params=None, env=None):
            if 'trade_svd_market_state' in sql:
                return svd_row
            if 'macro_data' in sql:
                return _make_qvix_row(10.0)
            if 'user_positions' in sql:
                return []
            return []

        with patch('config.db.execute_query', side_effect=fake_execute):
            result = _do_overview(USER_ID)

        assert result['svd']['is_mutation'] is False

    def test_mutation_flag_true_when_db_returns_one(self):
        svd_row = [{'calc_date': '2026-04-18', 'market_state': '齐涨齐跌',
                     'is_mutation': 1, 'top1_var_ratio': 0.55, 'top3_var_ratio': 0.80}]

        def fake_execute(sql, params=None, env=None):
            if 'trade_svd_market_state' in sql:
                return svd_row
            if 'macro_data' in sql:
                return _make_qvix_row(18.0)
            if 'user_positions' in sql:
                return []
            return []

        with patch('config.db.execute_query', side_effect=fake_execute):
            result = _do_overview(USER_ID)

        assert result['svd']['is_mutation'] is True

    def test_result_has_exactly_four_top_level_keys(self):
        def fake_execute(sql, params=None, env=None):
            if 'trade_svd_market_state' in sql:
                return []
            if 'macro_data' in sql:
                return []
            if 'user_positions' in sql:
                return []
            return []

        with patch('config.db.execute_query', side_effect=fake_execute):
            result = _do_overview(USER_ID)

        assert set(result.keys()) == {'svd', 'qvix', 'concentration', 'sector'}

    def test_stock_weights_capped_at_8(self):
        """stock_weights should return at most 8 items."""
        pos_rows = _make_pos_rows(
            *[(f'00000{i}.SZ', f'Stock{i}', 100, 10.0) for i in range(10)]
        )
        ind_rows = _make_ind_rows({f'00000{i}.SZ': '食品饮料' for i in range(10)})

        def fake_execute(sql, params=None, env=None):
            if 'trade_svd_market_state' in sql:
                return _make_svd_row()
            if 'macro_data' in sql:
                return _make_qvix_row(15.0)
            if 'user_positions' in sql:
                return pos_rows
            if 'trade_stock_basic' in sql:
                return ind_rows
            return []

        with patch('config.db.execute_query', side_effect=fake_execute):
            result = _do_overview(USER_ID)

        assert len(result['concentration']['stock_weights']) <= 8
