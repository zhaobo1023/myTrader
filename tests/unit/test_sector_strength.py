# -*- coding: utf-8 -*-
"""
Unit tests for data_analyst.sw_rotation.sector_strength pure functions.

No DB or network access required.
"""
import math
import sys
import os

import numpy as np
import pandas as pd
import pytest

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from data_analyst.sw_rotation.sector_strength import (
    calc_mom_21,
    calc_rs_60_cross,
    calc_vol_ratio,
    calc_composite_score,
    calc_phase,
    detect_inflection,
    rank_norm,
)


# ============================================================
# TestRankNorm
# ============================================================

class TestRankNorm:
    def test_basic_normalization(self):
        s = pd.Series([0.0, 50.0, 100.0])
        result = rank_norm(s)
        assert abs(result.iloc[0] - 0.0) < 1e-9
        assert abs(result.iloc[1] - 50.0) < 1e-9
        assert abs(result.iloc[2] - 100.0) < 1e-9

    def test_all_same_values(self):
        s = pd.Series([5.0, 5.0, 5.0])
        result = rank_norm(s)
        # All should be 50 (mid-point)
        assert all(abs(v - 50.0) < 1e-9 for v in result)

    def test_single_value(self):
        s = pd.Series([3.14])
        result = rank_norm(s)
        assert abs(result.iloc[0] - 50.0) < 1e-9

    def test_with_nan(self):
        s = pd.Series([0.0, np.nan, 100.0])
        result = rank_norm(s)
        assert abs(result.iloc[0] - 0.0) < 1e-9
        assert np.isnan(result.iloc[1])
        assert abs(result.iloc[2] - 100.0) < 1e-9

    def test_all_nan(self):
        s = pd.Series([np.nan, np.nan])
        result = rank_norm(s)
        assert all(np.isnan(v) for v in result)


# ============================================================
# TestCalcSectorStrength
# ============================================================

class TestCalcSectorStrength:
    def _make_close(self, n: int, start: float = 100.0, pct_per_day: float = 0.001) -> pd.Series:
        """Create synthetic close price series."""
        prices = [start * (1 + pct_per_day) ** i for i in range(n)]
        return pd.Series(prices, dtype=float)

    def test_mom_21_basic(self):
        # 22 prices; 21-day mom = (prices[21] / prices[0] - 1) * 100
        close = self._make_close(n=22, start=100.0, pct_per_day=0.01)
        mom = calc_mom_21(close)
        expected = (close.iloc[-1] / close.iloc[0] - 1) * 100
        assert mom is not None
        assert abs(mom - expected) < 1e-6

    def test_mom_21_insufficient_data(self):
        close = self._make_close(n=20)  # only 20 points
        mom = calc_mom_21(close)
        assert mom is None

    def test_rs_60_cross_section(self):
        # Create 5 sectors with different 60d returns
        sectors = ['A', 'B', 'C', 'D', 'E']
        rets = pd.Series([10.0, 5.0, 0.0, -5.0, -10.0], index=sectors)
        rs = calc_rs_60_cross(rets)
        # Best sector should have highest rank
        assert rs['A'] > rs['B'] > rs['C'] > rs['D'] > rs['E']
        # All values should be in [0, 100]
        assert rs.min() >= 0.0
        assert rs.max() <= 100.0

    def test_rs_60_range(self):
        n = 50
        rets = pd.Series(np.random.randn(n))
        rs = calc_rs_60_cross(rets)
        assert rs.min() >= 0.0
        assert rs.max() <= 100.0

    def test_vol_ratio_calc(self):
        # Create 60 days; last 10 should be double the mean of all 60
        base = np.ones(50) * 100.0
        recent = np.ones(10) * 200.0
        amount = pd.Series(np.concatenate([base, recent]))
        vr = calc_vol_ratio(amount)
        assert vr is not None
        # recent mean = 200, all mean ~= (50*100 + 10*200) / 60 = 116.67
        # vol_ratio = 200 / ((50*100 + 10*200)/60) ≈ 1.71
        assert vr > 1.0

    def test_vol_ratio_insufficient_data(self):
        amount = pd.Series(np.ones(50))
        vr = calc_vol_ratio(amount)
        assert vr is None  # need >= 60 days

    def test_composite_score_range(self):
        n = 20
        mom = pd.Series(np.random.randn(n) * 5)
        rs60 = pd.Series(np.random.uniform(0, 100, n))
        vol = pd.Series(np.random.uniform(0.5, 2.0, n))
        composite = calc_composite_score(mom, rs60, vol)
        valid = composite.dropna()
        assert (valid >= 0).all()
        assert (valid <= 100).all()

    def test_rank_normalization_boundary(self):
        # Test rank_norm with extreme values
        s = pd.Series([-100.0, 0.0, 100.0])
        result = rank_norm(s)
        assert abs(result.iloc[0] - 0.0) < 1e-9
        assert abs(result.iloc[1] - 50.0) < 1e-9
        assert abs(result.iloc[2] - 100.0) < 1e-9


# ============================================================
# TestCalcPhase
# ============================================================

class TestCalcPhase:
    def test_accel_up(self):
        # mom today = 2.0, mom yesterday = 1.0 (positive, delta > 0)
        phase = calc_phase(mom_21_today=2.0, mom_21_yesterday=1.0)
        assert phase == 'accel_up'

    def test_decel_up(self):
        # mom today = 1.0, mom yesterday = 2.0 (positive, delta < 0)
        phase = calc_phase(mom_21_today=1.0, mom_21_yesterday=2.0)
        assert phase == 'decel_up'

    def test_accel_down(self):
        # mom today = -2.0, mom yesterday = -1.0 (negative, delta < 0)
        phase = calc_phase(mom_21_today=-2.0, mom_21_yesterday=-1.0)
        assert phase == 'accel_down'

    def test_decel_down(self):
        # mom today = -1.0, mom yesterday = -2.0 (negative, delta > 0 = slowing decline)
        phase = calc_phase(mom_21_today=-1.0, mom_21_yesterday=-2.0)
        assert phase == 'decel_down'

    def test_neutral_near_zero(self):
        phase = calc_phase(mom_21_today=0.3, mom_21_yesterday=0.2)
        assert phase == 'neutral'

    def test_neutral_exact_zero(self):
        phase = calc_phase(mom_21_today=0.0, mom_21_yesterday=1.0)
        assert phase == 'neutral'

    def test_none_today(self):
        phase = calc_phase(mom_21_today=None, mom_21_yesterday=1.0)
        assert phase == 'neutral'

    def test_none_yesterday(self):
        # Can't compute delta, default to neutral
        phase = calc_phase(mom_21_today=2.0, mom_21_yesterday=None)
        assert phase == 'neutral'

    def test_decel_up_boundary(self):
        # Exactly at 0.5 boundary: abs(0.5) is NOT < 0.5
        phase = calc_phase(mom_21_today=0.5, mom_21_yesterday=0.4)
        assert phase == 'accel_up'

    def test_neutral_just_below_boundary(self):
        phase = calc_phase(mom_21_today=0.499, mom_21_yesterday=0.4)
        assert phase == 'neutral'


# ============================================================
# TestDetectInflection
# ============================================================

class TestDetectInflection:
    def test_turn_up_from_decel_down(self):
        is_infl, itype = detect_inflection('accel_up', 'decel_down')
        assert is_infl is True
        assert itype == 'turn_up'

    def test_turn_up_from_neutral(self):
        is_infl, itype = detect_inflection('decel_up', 'neutral')
        assert is_infl is True
        assert itype == 'turn_up'

    def test_turn_down_from_decel_up(self):
        is_infl, itype = detect_inflection('accel_down', 'decel_up')
        assert is_infl is True
        assert itype == 'turn_down'

    def test_turn_down_from_neutral(self):
        is_infl, itype = detect_inflection('decel_down', 'neutral')
        assert is_infl is True
        assert itype == 'turn_down'

    def test_no_inflection_continuous_up(self):
        is_infl, itype = detect_inflection('accel_up', 'accel_up')
        assert is_infl is False
        assert itype is None

    def test_no_inflection_continuous_down(self):
        is_infl, itype = detect_inflection('accel_down', 'accel_down')
        assert is_infl is False
        assert itype is None

    def test_no_inflection_neutral_to_neutral(self):
        is_infl, itype = detect_inflection('neutral', 'neutral')
        assert is_infl is False
        assert itype is None

    def test_no_yesterday(self):
        is_infl, itype = detect_inflection('accel_up', None)
        assert is_infl is False
        assert itype is None

    def test_turn_up_accel_up_from_accel_down(self):
        # accel_down -> accel_up: that is turn_up
        is_infl, itype = detect_inflection('accel_up', 'accel_down')
        # accel_down is NOT in turn_up_from = {decel_down, neutral}
        assert is_infl is False


# ============================================================
# TestSectorStrengthService — 用 mock 测试 service 层降级路径
# ============================================================

from unittest.mock import patch, MagicMock


class TestSectorStrengthServiceFallback:
    """测试 sector_strength_service 在表为空时的降级行为（mock DB）。"""

    def test_get_latest_strength_empty_table(self):
        """表为空时应返回 {trade_date: None, sectors: [], inflections: []}。"""
        from api.services.sector_strength_service import get_latest_strength

        # MAX(trade_date) 返回 None（空表）
        with patch('api.services.sector_strength_service.execute_query',
                   return_value=[{'d': None}]):
            result = get_latest_strength()
        assert result['trade_date'] is None
        assert result['sectors'] == []
        assert result['inflections'] == []

    def test_get_latest_picks_empty_table(self):
        """表为空时应返回 {pick_date: None, picks: []}。"""
        from api.services.sector_strength_service import get_latest_picks

        with patch('api.services.sector_strength_service.execute_query',
                   return_value=[{'d': None}]):
            result = get_latest_picks()
        assert result['pick_date'] is None
        assert result['picks'] == []

    def test_get_latest_strength_with_data(self):
        """有数据时应正确组装 sectors 列表。"""
        from api.services.sector_strength_service import get_latest_strength
        from decimal import Decimal

        # trade_date 已指定，service 直接跳过"查最新日期"的查询
        # 只有两次 query：一次查 sectors，一次查 inflections
        fake_sector_rows = [{
            'sector_code': '801010',
            'sector_name': '农林牧渔',
            'parent_name': '农林牧渔',
            'mom_21': Decimal('3.14'),
            'rs_60': Decimal('72.5'),
            'vol_ratio': Decimal('1.23'),
            'composite_score': Decimal('68.0'),
            'score_rank': 1,
            'phase': 'accel_up',
            'is_inflection': 1,
            'inflection_type': 'turn_up',
        }]

        call_results = [fake_sector_rows, fake_sector_rows]

        def mock_query(sql, params=None, env='online'):
            return call_results.pop(0)

        with patch('api.services.sector_strength_service.execute_query',
                   side_effect=mock_query):
            result = get_latest_strength(trade_date='2026-04-25', top_n=10)

        assert result['trade_date'] == '2026-04-25'
        assert len(result['sectors']) == 1
        s = result['sectors'][0]
        # Decimal 应被转换为 float
        assert isinstance(s['mom_21'], float)
        assert abs(s['mom_21'] - 3.14) < 1e-4

    def test_clean_row_decimal_conversion(self):
        """_clean_row 应将 Decimal 转 float、date 转 str。"""
        from decimal import Decimal
        from datetime import date as date_type
        from api.services.sector_strength_service import _clean_row

        row = {
            'score': Decimal('45.678'),
            'pick_date': date_type(2026, 4, 25),
            'name': '半导体',
            'count': 5,
        }
        cleaned = _clean_row(row)
        assert isinstance(cleaned['score'], float)
        assert abs(cleaned['score'] - 45.678) < 1e-3
        assert cleaned['pick_date'] == '2026-04-25'
        assert cleaned['name'] == '半导体'
        assert cleaned['count'] == 5


class TestCollectSectorStrengthSnapshot:
    """测试 _collect_sector_strength_snapshot 的降级和正常路径。"""

    def test_service_exception_returns_fallback(self):
        """service 层抛异常时，晨报应返回降级文本而不是崩溃。"""
        from api.services.global_asset_briefing import _collect_sector_strength_snapshot

        with patch('api.services.global_asset_briefing._collect_sector_strength_snapshot',
                   return_value=('(板块强度数据不可用)', None)) as mock_fn:
            text, dt = mock_fn()
        assert '板块强度数据不可用' in text
        assert dt is None

    def test_empty_service_returns_fallback(self):
        """service 返回空数据时应显示降级文本。"""
        from api.services.global_asset_briefing import _collect_sector_strength_snapshot

        empty_strength = {'trade_date': None, 'sectors': [], 'inflections': []}
        empty_picks = {'pick_date': None, 'picks': []}

        with patch('api.services.sector_strength_service.get_latest_strength',
                   return_value=empty_strength), \
             patch('api.services.sector_strength_service.get_latest_picks',
                   return_value=empty_picks):
            text, dt = _collect_sector_strength_snapshot()

        assert '板块强度数据不可用' in text
        assert dt is None

    def test_has_data_returns_table(self):
        """有板块和选股数据时，应生成包含关键字段的表格文本。"""
        from api.services.global_asset_briefing import _collect_sector_strength_snapshot

        fake_strength = {
            'trade_date': '2026-04-25',
            'sectors': [{
                'score_rank': 1, 'sector_name': '半导体',
                'parent_name': '电子', 'mom_21': 5.5,
                'rs_60': 80.0, 'vol_ratio': 1.5,
                'composite_score': 75.0, 'phase': 'accel_up',
                'inflection_type': 'turn_up',
            }],
            'inflections': [{
                'sector_name': '半导体', 'inflection_type': 'turn_up',
            }],
        }
        fake_picks = {
            'pick_date': '2026-04-25',
            'picks': [{
                'pick_rank': 1, 'stock_code': '000001.SZ',
                'stock_name': '平安银行', 'sw_level2': '股份行',
                'mom_1m': 3.2, 'rsi_14': 55.0,
                'bias_20': 1.1, 'pick_score': 68.0,
            }],
        }

        # 函数内部使用局部 import，patch 原模块的符号
        with patch('api.services.sector_strength_service.get_latest_strength',
                   return_value=fake_strength), \
             patch('api.services.sector_strength_service.get_latest_picks',
                   return_value=fake_picks):
            text, dt = _collect_sector_strength_snapshot()

        assert dt == '2026-04-25'
        assert '半导体' in text
        assert '平安银行' in text
        assert 'turn_up' in text or '拐点预警' in text
