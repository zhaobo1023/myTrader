# Five-Section Analysis Framework Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the complete five-section (技术/资金/基本面/情绪/资本周期) investment research framework under `research/` with DB persistence, scoring engines, and REST API endpoints.

**Architecture:** New `research/` package (fundamental / sentiment / composite / watchlist sub-packages) + Alembic migration for 5 DB tables + `api/routers/research.py` that exposes all endpoints. Reuses existing `investment_rag/report_engine/data_tools.py` for data access and `strategist/tech_scan/` for technical signals.

**Tech Stack:** Python 3.10, SQLAlchemy (raw `text()`), AKShare, pytest, FastAPI, Alembic (MySQL)

**Key existing assets to reuse:**
- `investment_rag/report_engine/data_tools.py` — `get_valuation_snapshot()`, `get_expected_return_context()`, `get_financial_data()`, `get_tech_analysis()`
- `strategist/tech_scan/` — `IndicatorCalculator`, `SignalDetector`, `DataFetcher`
- `config/db.py` — `execute_query()` / `execute_many()`
- `api/dependencies.py` — `get_db` async session

---

## Task 0: Alembic Migration — 5 Research Tables

**Files:**
- Create: `alembic/versions/a1b2c3d4e5f6_research_tables.py`

**Step 1: Create migration file**

```python
# alembic/versions/a1b2c3d4e5f6_research_tables.py
"""research tables: fundamental_snapshots, sentiment_scores, sentiment_events, composite_scores, watchlist

Revision ID: a1b2c3d4e5f6
Revises: 9dae0fdb5c83
Create Date: 2026-04-05
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = '9dae0fdb5c83'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('fundamental_snapshots',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(10), nullable=False),
        sa.Column('snap_date', sa.Date(), nullable=False),
        sa.Column('fundamental_score', sa.SmallInteger(), nullable=True),
        sa.Column('pe_ttm', sa.Numeric(8, 2), nullable=True),
        sa.Column('pe_quantile_5yr', sa.Numeric(5, 3), nullable=True),
        sa.Column('pb', sa.Numeric(6, 2), nullable=True),
        sa.Column('pb_quantile_5yr', sa.Numeric(5, 3), nullable=True),
        sa.Column('roe', sa.Numeric(6, 4), nullable=True),
        sa.Column('revenue_yoy', sa.Numeric(6, 4), nullable=True),
        sa.Column('profit_yoy', sa.Numeric(6, 4), nullable=True),
        sa.Column('fcf', sa.Numeric(14, 2), nullable=True),
        sa.Column('net_cash', sa.Numeric(14, 2), nullable=True),
        sa.Column('expected_return_2yr', sa.Numeric(6, 4), nullable=True),
        sa.Column('valuation_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_fundamental_code_date', 'fundamental_snapshots', ['code', 'snap_date'])

    op.create_table('sentiment_scores',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(20), nullable=False),
        sa.Column('score_date', sa.Date(), nullable=False),
        sa.Column('composite_score', sa.SmallInteger(), nullable=True),
        sa.Column('score_fund', sa.SmallInteger(), nullable=True),
        sa.Column('score_price_vol', sa.SmallInteger(), nullable=True),
        sa.Column('score_consensus', sa.SmallInteger(), nullable=True),
        sa.Column('score_sector', sa.SmallInteger(), nullable=True),
        sa.Column('score_macro', sa.SmallInteger(), nullable=True),
        sa.Column('historical_quantile', sa.Numeric(4, 3), nullable=True),
        sa.Column('label', sa.String(20), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_sentiment_score_code_date', 'sentiment_scores', ['code', 'score_date'])

    op.create_table('sentiment_events',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(20), nullable=False),
        sa.Column('event_date', sa.Date(), nullable=False),
        sa.Column('event_text', sa.String(300), nullable=False),
        sa.Column('direction', sa.Enum('positive', 'negative', 'neutral', name='event_direction'), nullable=False),
        sa.Column('magnitude', sa.Enum('high', 'medium', 'low', name='event_magnitude'), nullable=False),
        sa.Column('category', sa.Enum('capital', 'earnings', 'policy', 'geopolitical', 'industry', 'technical', 'shareholder', name='event_category'), nullable=False),
        sa.Column('is_verified', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('verified_result', sa.String(200), nullable=True),
        sa.Column('source', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_sentiment_event_code', 'sentiment_events', ['code'])
    op.create_index('idx_sentiment_event_date', 'sentiment_events', ['event_date'])

    op.create_table('composite_scores',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(20), nullable=False),
        sa.Column('score_date', sa.Date(), nullable=False),
        sa.Column('score_technical', sa.SmallInteger(), nullable=True),
        sa.Column('score_fund_flow', sa.SmallInteger(), nullable=True),
        sa.Column('score_fundamental', sa.SmallInteger(), nullable=True),
        sa.Column('score_sentiment', sa.SmallInteger(), nullable=True),
        sa.Column('score_capital_cycle', sa.SmallInteger(), nullable=True),
        sa.Column('composite_score', sa.SmallInteger(), nullable=True),
        sa.Column('direction', sa.Enum('strong_bull', 'bull', 'neutral', 'bear', 'strong_bear', name='composite_direction'), nullable=True),
        sa.Column('phase', sa.SmallInteger(), nullable=True),
        sa.Column('key_signal', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_composite_code_date', 'composite_scores', ['code', 'score_date'])

    op.create_table('watchlist',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(20), nullable=False),
        sa.Column('name', sa.String(100), nullable=True),
        sa.Column('tier', sa.Enum('deep', 'standard', 'watch', name='watchlist_tier'), server_default='watch', nullable=False),
        sa.Column('industry', sa.String(50), nullable=True),
        sa.Column('added_date', sa.Date(), nullable=True),
        sa.Column('profile_yaml', sa.Text(), nullable=True),
        sa.Column('current_thesis', sa.Text(), nullable=True),
        sa.Column('thesis_updated_at', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', name='uk_watchlist_code'),
    )


def downgrade() -> None:
    op.drop_table('watchlist')
    op.drop_index('idx_composite_code_date', table_name='composite_scores')
    op.drop_table('composite_scores')
    op.drop_index('idx_sentiment_event_date', table_name='sentiment_events')
    op.drop_index('idx_sentiment_event_code', table_name='sentiment_events')
    op.drop_table('sentiment_events')
    op.drop_index('idx_sentiment_score_code_date', table_name='sentiment_scores')
    op.drop_table('sentiment_scores')
    op.drop_index('idx_fundamental_code_date', table_name='fundamental_snapshots')
    op.drop_table('fundamental_snapshots')
    op.execute('DROP TYPE IF EXISTS composite_direction')
    op.execute('DROP TYPE IF EXISTS watchlist_tier')
    op.execute('DROP TYPE IF EXISTS event_category')
    op.execute('DROP TYPE IF EXISTS event_magnitude')
    op.execute('DROP TYPE IF EXISTS event_direction')
```

**Step 2: Verify (no run needed — migration runs via `make migrate` in prod)**

```bash
python -c "import ast; ast.parse(open('alembic/versions/a1b2c3d4e5f6_research_tables.py').read()); print('syntax OK')"
```

**Step 3: Commit**

```bash
git add alembic/versions/a1b2c3d4e5f6_research_tables.py
git commit -m "feat(db): add 5 research tables migration"
```

---

## Task 1: research/ Package Structure

**Files to create (all empty except `__init__.py` with docstring):**
- `research/__init__.py`
- `research/fundamental/__init__.py`
- `research/sentiment/__init__.py`
- `research/composite/__init__.py`
- `research/watchlist/__init__.py`

**Step 1: Create all `__init__.py` files**

Each file contains only:
```python
# -*- coding: utf-8 -*-
```

**Step 2: Verify importable**
```bash
python -c "import research; import research.fundamental; import research.sentiment; import research.composite; import research.watchlist; print('OK')"
```

**Step 3: Commit**
```bash
git add research/
git commit -m "feat(research): scaffold five-section package structure"
```

---

## Task 2: FundamentalValuator — 8-Method Valuation

**Files:**
- Create: `research/fundamental/valuation.py`
- Create: `research/fundamental/tests/__init__.py`
- Create: `research/fundamental/tests/test_valuation.py`

**What it does:** Given a stock code, compute 8 valuation methods and return a dict with `fair_market_cap` (亿元), `vs_current` (premium fraction), and `notes` for each method. Uses `trade_stock_daily_basic` for price data and `AKShareLoader` for financials.

**Data needed (from existing sources):**
- `trade_stock_daily_basic`: `pe_ttm`, `pb`, `total_mv` (万元), `dv_ttm` (dividend yield %), `close`
- Historical PE/PB series (5yr) for quantile → already in `data_tools.get_valuation_snapshot()`
- `AKShareLoader.get_financial_summary()`: `net_profit_ttm`, `total_assets`, `total_liabilities`, `net_assets`, `operating_cashflow`, `capex`, `revenue_ttm`

**Step 1: Write tests first**

```python
# research/fundamental/tests/test_valuation.py
# -*- coding: utf-8 -*-
import pytest
from unittest.mock import patch, MagicMock
from research.fundamental.valuation import FundamentalValuator, ValuationResult


@pytest.fixture
def mock_market_data():
    return {
        'pe_ttm': 20.0,
        'pb': 2.5,
        'total_mv': 5000000.0,   # 万元 = 5000亿
        'dv_ttm': 2.0,            # 2% dividend yield
        'close': 100.0,
    }

@pytest.fixture
def mock_financial_data():
    return {
        'net_profit_ttm': 25_0000_0000,   # 25亿
        'total_assets': 200_0000_0000,
        'total_liabilities': 100_0000_0000,
        'net_assets': 100_0000_0000,
        'operating_cashflow': 30_0000_0000,
        'capex': 10_0000_0000,
        'revenue_ttm': 200_0000_0000,
    }

@pytest.fixture
def mock_pe_series():
    import pandas as pd
    return pd.Series([15.0, 18.0, 22.0, 25.0, 30.0, 20.0, 17.0])


def _make_valuator(mock_market_data, mock_financial_data, mock_pe_series):
    v = FundamentalValuator.__new__(FundamentalValuator)
    v._get_market_data = MagicMock(return_value=mock_market_data)
    v._get_financial_data = MagicMock(return_value=mock_financial_data)
    v._get_pe_series = MagicMock(return_value=mock_pe_series)
    return v


def test_valuation_result_has_8_methods(mock_market_data, mock_financial_data, mock_pe_series):
    v = _make_valuator(mock_market_data, mock_financial_data, mock_pe_series)
    result = v.compute('300750')
    assert len(result.methods) == 8
    names = [m['method'] for m in result.methods]
    assert 'PE-earnings' in names
    assert 'PB-netasset' in names
    assert 'FCF-yield' in names
    assert 'DCF-3stage' in names
    assert 'Gordon-implied-g' in names
    assert 'Ceiling-matrix' in names
    assert 'Liquidation' in names
    assert 'Replacement' in names


def test_pe_earnings_valuation(mock_market_data, mock_financial_data, mock_pe_series):
    v = _make_valuator(mock_market_data, mock_financial_data, mock_pe_series)
    result = v.compute('300750')
    pe_method = next(m for m in result.methods if m['method'] == 'PE-earnings')
    # fair_pe = 40th percentile of pe_series; net_profit_ttm = 25亿
    # fair_market_cap should be a positive number in 亿
    assert pe_method['fair_market_cap_yi'] > 0
    assert isinstance(pe_method['vs_current'], float)


def test_gordon_implied_g_formula(mock_market_data, mock_financial_data, mock_pe_series):
    v = _make_valuator(mock_market_data, mock_financial_data, mock_pe_series)
    result = v.compute('300750')
    gordon = next(m for m in result.methods if m['method'] == 'Gordon-implied-g')
    # With PE=20, cost_of_equity=8%: implied_g = 8% - 1/20 = 8% - 5% = 3%
    assert abs(gordon['implied_growth_rate'] - 0.03) < 0.001


def test_ceiling_matrix_returns_9_scenarios(mock_market_data, mock_financial_data, mock_pe_series):
    v = _make_valuator(mock_market_data, mock_financial_data, mock_pe_series)
    result = v.compute('300750')
    ceiling = next(m for m in result.methods if m['method'] == 'Ceiling-matrix')
    assert len(ceiling['scenarios']) == 9


def test_missing_financial_data_returns_none_methods(mock_market_data, mock_pe_series):
    v = FundamentalValuator.__new__(FundamentalValuator)
    v._get_market_data = MagicMock(return_value=mock_market_data)
    v._get_financial_data = MagicMock(return_value=None)
    v._get_pe_series = MagicMock(return_value=mock_pe_series)
    result = v.compute('000001')
    # PE-based still works (only needs pe_ttm and pe_series), financial-based should be None
    fcf = next(m for m in result.methods if m['method'] == 'FCF-yield')
    assert fcf['fair_market_cap_yi'] is None
```

**Step 2: Run tests to verify they fail**
```bash
python -m pytest research/fundamental/tests/test_valuation.py -v 2>&1 | head -20
```
Expected: ImportError (module not created yet)

**Step 3: Implement `research/fundamental/valuation.py`**

```python
# -*- coding: utf-8 -*-
"""
FundamentalValuator — 8-method parallel valuation calculator.

Methods:
  1. PE-earnings     PE × TTM profit; fair PE = 40th-pct of 5yr history
  2. PB-netasset     PB × net assets; fair PB = 40th-pct of 5yr history
  3. FCF-yield       FCF / market_cap vs 6% hurdle
  4. DCF-3stage      3-stage DCF with configurable growth rates
  5. Gordon-implied-g  Reverse-engineer implied perpetual growth from current PE
  6. Ceiling-matrix  3x3 revenue_share x net_margin x PE scenarios
  7. Liquidation     (total_assets * 0.60 - liabilities) as floor
  8. Replacement     (total_assets * 0.80 - liabilities) as floor
"""
import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

logger = logging.getLogger('myTrader.research')

# Constants
COST_OF_EQUITY = 0.08          # Gordon model discount rate
FAIR_PE_QUANTILE = 0.40        # 40th percentile = "reasonable" PE
FAIR_PB_QUANTILE = 0.40
FCF_HURDLE = 0.06              # 6% FCF yield = fair value
LIQUIDATION_HAIRCUT = 0.60     # 60 cents on the dollar
REPLACEMENT_HAIRCUT = 0.80
YI = 1_0000_0000               # 1亿 in yuan
WAN_YI = 1_0000_0000_0000      # 1万亿


@dataclass
class ValuationResult:
    code: str
    current_market_cap_yi: float            # 亿元
    methods: list[dict[str, Any]] = field(default_factory=list)
    notes: str = ''


class FundamentalValuator:
    """Compute 8-method parallel valuation for a stock."""

    def __init__(self):
        pass

    def compute(self, code: str,
                dcf_growth1: float = 0.15, dcf_growth2: float = 0.08,
                dcf_years1: int = 5, dcf_years2: int = 5,
                dcf_terminal_growth: float = 0.03,
                ceiling_rev_shares: list[float] | None = None,
                ceiling_margins: list[float] | None = None,
                ceiling_pes: list[float] | None = None,
                ) -> ValuationResult:
        """Return ValuationResult with 8 methods for `code`."""
        market = self._get_market_data(code)
        financials = self._get_financial_data(code)
        pe_series = self._get_pe_series(code)

        if not market:
            return ValuationResult(code=code, current_market_cap_yi=0.0,
                                   notes='No market data found')

        current_mv_yi = market['total_mv'] / 10_000.0  # 万元 -> 亿元

        result = ValuationResult(code=code, current_market_cap_yi=current_mv_yi)

        # --- Helper ---
        def _vs(fair_yi):
            if fair_yi is None or current_mv_yi <= 0:
                return None
            return round(fair_yi / current_mv_yi - 1, 4)

        # 1. PE-earnings
        fair_pe = float(pe_series.quantile(FAIR_PE_QUANTILE)) if pe_series is not None and len(pe_series) >= 5 else None
        if fair_pe and financials:
            net_profit_yi = financials['net_profit_ttm'] / YI
            fair_mv1 = fair_pe * net_profit_yi
            result.methods.append({
                'method': 'PE-earnings',
                'fair_pe': round(fair_pe, 1),
                'fair_market_cap_yi': round(fair_mv1, 1),
                'vs_current': _vs(fair_mv1),
                'note': f'fair PE ({FAIR_PE_QUANTILE*100:.0f}th pct) x TTM profit',
            })
        else:
            result.methods.append({'method': 'PE-earnings', 'fair_market_cap_yi': None,
                                   'vs_current': None, 'note': 'insufficient data'})

        # 2. PB-netasset
        pb_series = self._get_pb_series(code)
        fair_pb = float(pb_series.quantile(FAIR_PB_QUANTILE)) if pb_series is not None and len(pb_series) >= 5 else None
        if fair_pb and financials:
            net_assets_yi = financials['net_assets'] / YI
            fair_mv2 = fair_pb * net_assets_yi
            result.methods.append({
                'method': 'PB-netasset',
                'fair_pb': round(fair_pb, 2),
                'fair_market_cap_yi': round(fair_mv2, 1),
                'vs_current': _vs(fair_mv2),
                'note': f'fair PB ({FAIR_PB_QUANTILE*100:.0f}th pct) x book value',
            })
        else:
            result.methods.append({'method': 'PB-netasset', 'fair_market_cap_yi': None,
                                   'vs_current': None, 'note': 'insufficient data'})

        # 3. FCF-yield  (fair value = FCF / FCF_HURDLE)
        if financials:
            fcf = financials.get('operating_cashflow', 0) - financials.get('capex', 0)
            fcf_yi = fcf / YI
            fair_mv3 = fcf_yi / FCF_HURDLE if fcf > 0 else None
            fcf_yield = fcf / (current_mv_yi * YI) if current_mv_yi > 0 else None
            result.methods.append({
                'method': 'FCF-yield',
                'fcf_yi': round(fcf_yi, 1),
                'current_fcf_yield': round(fcf_yield * 100, 2) if fcf_yield else None,
                'fair_market_cap_yi': round(fair_mv3, 1) if fair_mv3 else None,
                'vs_current': _vs(fair_mv3),
                'note': f'FCF / {FCF_HURDLE*100:.0f}% hurdle rate',
            })
        else:
            result.methods.append({'method': 'FCF-yield', 'fair_market_cap_yi': None,
                                   'vs_current': None, 'note': 'insufficient data'})

        # 4. DCF-3stage
        if financials:
            fcf_base = (financials.get('operating_cashflow', 0) - financials.get('capex', 0)) / YI
            if fcf_base > 0:
                pv = 0.0
                cf = fcf_base
                for yr in range(1, dcf_years1 + 1):
                    cf *= (1 + dcf_growth1)
                    pv += cf / (1 + COST_OF_EQUITY) ** yr
                for yr in range(1, dcf_years2 + 1):
                    cf *= (1 + dcf_growth2)
                    pv += cf / (1 + COST_OF_EQUITY) ** (dcf_years1 + yr)
                terminal = cf * (1 + dcf_terminal_growth) / (COST_OF_EQUITY - dcf_terminal_growth)
                terminal_pv = terminal / (1 + COST_OF_EQUITY) ** (dcf_years1 + dcf_years2)
                fair_mv4 = pv + terminal_pv
                result.methods.append({
                    'method': 'DCF-3stage',
                    'stage1_growth': dcf_growth1,
                    'stage2_growth': dcf_growth2,
                    'terminal_growth': dcf_terminal_growth,
                    'fair_market_cap_yi': round(fair_mv4, 1),
                    'vs_current': _vs(fair_mv4),
                    'note': f'S1:{dcf_growth1*100:.0f}%x{dcf_years1}yr S2:{dcf_growth2*100:.0f}%x{dcf_years2}yr T:{dcf_terminal_growth*100:.0f}%',
                })
            else:
                result.methods.append({'method': 'DCF-3stage', 'fair_market_cap_yi': None,
                                       'vs_current': None, 'note': 'negative FCF'})
        else:
            result.methods.append({'method': 'DCF-3stage', 'fair_market_cap_yi': None,
                                   'vs_current': None, 'note': 'insufficient data'})

        # 5. Gordon-implied-g  (implied_g = COST_OF_EQUITY - 1/PE)
        pe = market.get('pe_ttm')
        if pe and pe > 0:
            implied_g = COST_OF_EQUITY - 1.0 / pe
            result.methods.append({
                'method': 'Gordon-implied-g',
                'current_pe': pe,
                'cost_of_equity': COST_OF_EQUITY,
                'implied_growth_rate': round(implied_g, 4),
                'fair_market_cap_yi': None,   # this is diagnostic, not a price target
                'vs_current': None,
                'note': f'implied perpetual growth = {COST_OF_EQUITY*100:.0f}% - 1/PE',
            })
        else:
            result.methods.append({'method': 'Gordon-implied-g', 'fair_market_cap_yi': None,
                                   'vs_current': None, 'note': 'invalid PE'})

        # 6. Ceiling-matrix  3x3 revenue_share x net_margin x PE scenarios
        if financials:
            rev = financials.get('revenue_ttm', 0) / YI
            shares = ceiling_rev_shares or [0.8, 1.0, 1.3]     # relative to current revenue
            margins = ceiling_margins or [0.08, 0.12, 0.16]     # net margin scenarios
            pes = ceiling_pes or [15.0, 20.0, 25.0]             # exit PE scenarios
            scenarios = []
            for s in shares:
                for m in margins:
                    for p in pes:
                        fair = rev * s * m * p
                        scenarios.append({
                            'rev_mult': s, 'net_margin': m, 'exit_pe': p,
                            'fair_market_cap_yi': round(fair, 1),
                            'vs_current': _vs(fair),
                        })
            result.methods.append({
                'method': 'Ceiling-matrix',
                'scenarios': scenarios,
                'fair_market_cap_yi': scenarios[4]['fair_market_cap_yi'],  # mid scenario
                'vs_current': scenarios[4]['vs_current'],
                'note': '3x3 rev_share x margin x PE; mid=scenarios[4]',
            })
        else:
            result.methods.append({'method': 'Ceiling-matrix', 'fair_market_cap_yi': None,
                                   'vs_current': None, 'note': 'insufficient data'})

        # 7. Liquidation  (assets * 0.6 - liabilities)
        if financials:
            assets_yi = financials['total_assets'] / YI
            liab_yi = financials['total_liabilities'] / YI
            fair_mv7 = max(0, assets_yi * LIQUIDATION_HAIRCUT - liab_yi)
            result.methods.append({
                'method': 'Liquidation',
                'fair_market_cap_yi': round(fair_mv7, 1),
                'vs_current': _vs(fair_mv7),
                'note': f'total_assets x {LIQUIDATION_HAIRCUT} - liabilities (floor)',
            })
        else:
            result.methods.append({'method': 'Liquidation', 'fair_market_cap_yi': None,
                                   'vs_current': None, 'note': 'insufficient data'})

        # 8. Replacement  (assets * 0.8 - liabilities)
        if financials:
            fair_mv8 = max(0, assets_yi * REPLACEMENT_HAIRCUT - liab_yi)
            result.methods.append({
                'method': 'Replacement',
                'fair_market_cap_yi': round(fair_mv8, 1),
                'vs_current': _vs(fair_mv8),
                'note': f'total_assets x {REPLACEMENT_HAIRCUT} - liabilities',
            })
        else:
            result.methods.append({'method': 'Replacement', 'fair_market_cap_yi': None,
                                   'vs_current': None, 'note': 'insufficient data'})

        return result

    # ------------------------------------------------------------------ data
    def _get_market_data(self, code: str) -> dict | None:
        """Latest row from trade_stock_daily_basic."""
        try:
            from config.db import execute_query
            tushare_code = _to_tushare(code)
            rows = execute_query(
                "SELECT pe_ttm, pb, total_mv, dv_ttm, close "
                "FROM trade_stock_daily_basic WHERE ts_code=%s "
                "ORDER BY trade_date DESC LIMIT 1",
                (tushare_code,), env='online'
            )
            if not rows:
                return None
            r = rows[0]
            return {
                'pe_ttm': float(r['pe_ttm']) if r['pe_ttm'] else None,
                'pb': float(r['pb']) if r['pb'] else None,
                'total_mv': float(r['total_mv']) if r['total_mv'] else 0.0,
                'dv_ttm': float(r['dv_ttm']) if r['dv_ttm'] else 0.0,
                'close': float(r['close']) if r['close'] else 0.0,
            }
        except Exception as e:
            logger.error('[VALUATION] _get_market_data failed: %s', e)
            return None

    def _get_financial_data(self, code: str) -> dict | None:
        """Load financials via AKShareLoader; map to standard keys."""
        try:
            from investment_rag.ingest.loaders.akshare_loader import AKShareLoader
            loader = AKShareLoader()
            summary = loader.get_financial_summary(code)
            if not summary:
                return None
            return {
                'net_profit_ttm': float(summary.get('net_profit', 0) or 0),
                'total_assets': float(summary.get('total_assets', 0) or 0),
                'total_liabilities': float(summary.get('total_liab', 0) or 0),
                'net_assets': float(summary.get('total_hldr_eqy_inc_min_int', 0) or 0),
                'operating_cashflow': float(summary.get('n_cashflow_act', 0) or 0),
                'capex': float(summary.get('c_pay_acq_const_fiolta', 0) or 0),
                'revenue_ttm': float(summary.get('total_revenue', 0) or 0),
            }
        except Exception as e:
            logger.error('[VALUATION] _get_financial_data failed: %s', e)
            return None

    def _get_pe_series(self, code: str, years: int = 5) -> pd.Series | None:
        """Historical PE series from trade_stock_daily_basic."""
        return _fetch_ratio_series(code, 'pe_ttm', years)

    def _get_pb_series(self, code: str, years: int = 5) -> pd.Series | None:
        return _fetch_ratio_series(code, 'pb', years)


def _to_tushare(code: str) -> str:
    """'300750' -> '300750.SZ', '600519' -> '600519.SH'"""
    if '.' in code:
        return code
    return f"{code}.SZ" if code.startswith(('0', '3')) else f"{code}.SH"


def _fetch_ratio_series(code: str, col: str, years: int) -> pd.Series | None:
    try:
        from config.db import execute_query
        tushare_code = _to_tushare(code)
        rows = execute_query(
            f"SELECT {col} FROM trade_stock_daily_basic "
            f"WHERE ts_code=%s AND trade_date >= DATE_SUB(NOW(), INTERVAL %s YEAR) "
            f"AND {col} > 0 AND {col} < 9999",
            (tushare_code, years), env='online'
        )
        if not rows:
            return None
        values = [float(r[col]) for r in rows if r[col]]
        return pd.Series(values) if values else None
    except Exception as e:
        logger.error('[VALUATION] _fetch_ratio_series(%s, %s) failed: %s', code, col, e)
        return None
```

**Step 4: Run tests**
```bash
python -m pytest research/fundamental/tests/test_valuation.py -v
```
Expected: 5 PASS

**Step 5: Commit**
```bash
git add research/fundamental/valuation.py research/fundamental/tests/
git commit -m "feat(research): FundamentalValuator 8-method parallel valuation"
```

---

## Task 3: FundamentalScorer — 0-100 Scoring Engine

**Files:**
- Create: `research/fundamental/scorer.py`
- Create: `research/fundamental/tests/test_scorer.py`

**Scoring formula:** `fundamental_score = earnings_quality(40%) + valuation_attractiveness(40%) + growth_certainty(20%)`

**Step 1: Write tests**

```python
# research/fundamental/tests/test_scorer.py
# -*- coding: utf-8 -*-
import pytest
from unittest.mock import MagicMock
from research.fundamental.scorer import FundamentalScorer, ScorerInput


def _make_input(**kwargs):
    defaults = dict(
        pe_quantile=0.30,
        pb_quantile=0.25,
        fcf_yield=0.05,
        roe=0.18,
        roe_prev=0.15,
        ocf_to_profit=1.1,
        debt_ratio=0.45,
        revenue_yoy=0.15,
        profit_yoy=0.20,
    )
    defaults.update(kwargs)
    return ScorerInput(**defaults)


def test_low_pe_quantile_gives_high_valuation_score():
    inp = _make_input(pe_quantile=0.10)
    s = FundamentalScorer().score(inp)
    assert s.valuation_score >= 35


def test_high_pe_quantile_gives_low_valuation_score():
    inp = _make_input(pe_quantile=0.90)
    s = FundamentalScorer().score(inp)
    assert s.valuation_score <= 15


def test_high_roe_improving_gives_high_earnings_quality():
    inp = _make_input(roe=0.25, roe_prev=0.20, ocf_to_profit=1.2)
    s = FundamentalScorer().score(inp)
    assert s.earnings_quality_score >= 30


def test_composite_score_between_0_and_100():
    inp = _make_input()
    s = FundamentalScorer().score(inp)
    assert 0 <= s.composite_score <= 100


def test_score_label_mapping():
    # high score -> 优质
    inp_high = _make_input(pe_quantile=0.05, roe=0.30, roe_prev=0.25,
                           ocf_to_profit=1.5, revenue_yoy=0.30, profit_yoy=0.35)
    s_high = FundamentalScorer().score(inp_high)
    assert s_high.label in ('优质', '良好')

    # low score -> 一般 or 偏弱
    inp_low = _make_input(pe_quantile=0.95, roe=0.03, roe_prev=0.05,
                          ocf_to_profit=0.3, revenue_yoy=-0.05, profit_yoy=-0.10)
    s_low = FundamentalScorer().score(inp_low)
    assert s_low.label in ('一般', '偏弱', '较差')
```

**Step 2: Implement `research/fundamental/scorer.py`**

```python
# -*- coding: utf-8 -*-
"""FundamentalScorer — compute 0-100 fundamental score from structured inputs."""
from dataclasses import dataclass


@dataclass
class ScorerInput:
    # Valuation
    pe_quantile: float | None = None        # 0..1
    pb_quantile: float | None = None        # 0..1
    fcf_yield: float | None = None          # e.g. 0.05 = 5%
    # Earnings quality
    roe: float | None = None                # e.g. 0.18
    roe_prev: float | None = None           # previous year ROE
    ocf_to_profit: float | None = None      # OCF / net profit
    debt_ratio: float | None = None         # total_liab / total_assets
    # Growth
    revenue_yoy: float | None = None
    profit_yoy: float | None = None


@dataclass
class ScoreResult:
    earnings_quality_score: int     # 0..40
    valuation_score: int            # 0..40
    growth_score: int               # 0..20
    composite_score: int            # 0..100
    label: str


_LABELS = [(85, '优质'), (70, '良好'), (55, '中性'), (40, '一般'), (25, '偏弱'), (0, '较差')]


class FundamentalScorer:

    def score(self, inp: ScorerInput) -> ScoreResult:
        eq = self._earnings_quality(inp)
        va = self._valuation_attractiveness(inp)
        gr = self._growth_certainty(inp)
        composite = min(100, max(0, eq + va + gr))
        label = next(lbl for threshold, lbl in _LABELS if composite >= threshold)
        return ScoreResult(eq, va, gr, composite, label)

    # ---------------------------------------------------------------- sub-scores
    def _earnings_quality(self, inp: ScorerInput) -> int:
        """0..40"""
        score = 20  # neutral start

        # ROE level and trend (0..25)
        roe = inp.roe or 0
        if roe >= 0.25:
            score += 15
        elif roe >= 0.20:
            score += 10
        elif roe >= 0.15:
            score += 5
        elif roe < 0.05:
            score -= 10

        if inp.roe_prev is not None:
            if roe > inp.roe_prev:
                score += 5
            elif roe < inp.roe_prev - 0.03:
                score -= 5

        # OCF quality (-10..+10)
        ocf = inp.ocf_to_profit
        if ocf is not None:
            if ocf >= 1.2:
                score += 10
            elif ocf >= 0.8:
                score += 5
            elif ocf < 0.5:
                score -= 10

        # Leverage (-5..0)
        dr = inp.debt_ratio
        if dr is not None and dr > 0.70:
            score -= 5

        return min(40, max(0, score))

    def _valuation_attractiveness(self, inp: ScorerInput) -> int:
        """0..40; PE quantile drives 25 pts, PB quantile 10 pts, FCF yield 5 pts"""
        score = 0

        # PE quantile: linear: 0%→25, 50%→12, 100%→-10
        pq = inp.pe_quantile
        if pq is not None:
            score += round(25 - 35 * pq)

        # PB quantile: similar but 10pt range
        pbq = inp.pb_quantile
        if pbq is not None:
            score += round(10 - 15 * pbq)

        # FCF yield bonus
        fy = inp.fcf_yield
        if fy is not None:
            if fy >= 0.08:
                score += 5
            elif fy >= 0.05:
                score += 2

        return min(40, max(0, score))

    def _growth_certainty(self, inp: ScorerInput) -> int:
        """0..20"""
        score = 10  # neutral

        rev = inp.revenue_yoy or 0
        if rev >= 0.30:
            score += 6
        elif rev >= 0.15:
            score += 3
        elif rev < 0:
            score -= 5

        prt = inp.profit_yoy or 0
        if prt >= 0.30:
            score += 4
        elif prt >= 0.15:
            score += 2
        elif prt < 0:
            score -= 4

        return min(20, max(0, score))
```

**Step 3: Run tests**
```bash
python -m pytest research/fundamental/tests/test_scorer.py -v
```
Expected: 5 PASS

**Step 4: Commit**
```bash
git add research/fundamental/scorer.py research/fundamental/tests/test_scorer.py
git commit -m "feat(research): FundamentalScorer 0-100 scoring engine"
```

---

## Task 4: FundamentalSnapshot — DB Weekly Writer

**Files:**
- Create: `research/fundamental/snapshot.py`
- Create: `research/fundamental/tests/test_snapshot.py`

**What it does:** Given a stock code, pulls data from `FundamentalValuator` + `FundamentalScorer`, combines with `data_tools.get_valuation_snapshot()`, and upserts a row into `fundamental_snapshots`.

**Step 1: Write tests**

```python
# research/fundamental/tests/test_snapshot.py
# -*- coding: utf-8 -*-
import json
import pytest
from unittest.mock import patch, MagicMock
from research.fundamental.snapshot import FundamentalSnapshot


@pytest.fixture
def mock_snap():
    snap = FundamentalSnapshot.__new__(FundamentalSnapshot)
    snap._valuator = MagicMock()
    snap._scorer = MagicMock()
    snap._tools = MagicMock()
    return snap


def test_build_row_returns_dict_with_required_keys(mock_snap):
    from research.fundamental.valuation import ValuationResult
    from research.fundamental.scorer import ScoreResult, ScorerInput

    mock_snap._valuator.compute.return_value = ValuationResult(
        code='300750', current_market_cap_yi=5000.0,
        methods=[{'method': 'PE-earnings', 'fair_market_cap_yi': 4000.0,
                  'vs_current': -0.2, 'note': ''}],
    )
    mock_snap._scorer.score.return_value = ScoreResult(25, 30, 12, 67, '良好')
    mock_snap._get_financials_for_scorer.return_value = MagicMock()
    mock_snap._build_scorer_input = MagicMock(return_value=MagicMock())

    row = mock_snap._build_row('300750')
    assert 'code' in row
    assert 'snap_date' in row
    assert 'fundamental_score' in row
    assert 'valuation_json' in row
    val_data = json.loads(row['valuation_json'])
    assert len(val_data['methods']) == 1


def test_upsert_calls_execute_query(mock_snap):
    with patch('research.fundamental.snapshot.execute_query') as mock_eq, \
         patch.object(mock_snap, '_build_row', return_value={
             'code': '300750', 'snap_date': '2026-04-05',
             'fundamental_score': 67, 'pe_ttm': 20.0,
             'pe_quantile_5yr': 0.30, 'pb': 2.5,
             'pb_quantile_5yr': 0.25, 'roe': 0.18,
             'revenue_yoy': 0.15, 'profit_yoy': 0.20,
             'fcf': 10.0, 'net_cash': 5.0,
             'expected_return_2yr': 0.25,
             'valuation_json': '{}',
         }):
        mock_eq.return_value = None
        mock_snap.save('300750')
        mock_eq.assert_called_once()
```

**Step 2: Implement `research/fundamental/snapshot.py`**

```python
# -*- coding: utf-8 -*-
"""FundamentalSnapshot — pull, score, and persist a fundamental snapshot to DB."""
import json
import logging
from datetime import date

logger = logging.getLogger('myTrader.research')

try:
    from config.db import execute_query
except ImportError:
    execute_query = None


class FundamentalSnapshot:

    def __init__(self):
        from research.fundamental.valuation import FundamentalValuator
        from research.fundamental.scorer import FundamentalScorer
        from investment_rag.report_engine.data_tools import ReportDataTools
        self._valuator = FundamentalValuator()
        self._scorer = FundamentalScorer()
        self._tools = ReportDataTools()

    def save(self, code: str, snap_date: date | None = None) -> dict:
        """Build and upsert one snapshot row. Returns the row dict."""
        row = self._build_row(code, snap_date or date.today())
        self._upsert(row)
        logger.info('[SNAPSHOT] saved fundamental snapshot for %s on %s', code, row['snap_date'])
        return row

    def save_batch(self, codes: list[str]) -> list[str]:
        """Save snapshots for a list of codes. Returns list of successful codes."""
        ok = []
        for code in codes:
            try:
                self.save(code)
                ok.append(code)
            except Exception as e:
                logger.error('[SNAPSHOT] failed for %s: %s', code, e)
        return ok

    # ---------------------------------------------------------------- internals
    def _build_row(self, code: str, snap_date: date | None = None) -> dict:
        snap_date = snap_date or date.today()

        # Valuation (8 methods)
        val_result = self._valuator.compute(code)

        # Financial data for scorer
        fin = self._valuator._get_financial_data(code) or {}
        market = self._valuator._get_market_data(code) or {}
        pe_series = self._valuator._get_pe_series(code)
        pb_series = self._valuator._get_pb_series(code)

        import pandas as pd
        pe_q = float(pe_series.rank(pct=True).iloc[-1]) if pe_series is not None and len(pe_series) > 0 else None
        pb_q = float(pb_series.rank(pct=True).iloc[-1]) if pb_series is not None and len(pb_series) > 0 else None

        # Actually compute quantile of current PE within history
        current_pe = market.get('pe_ttm')
        if pe_series is not None and current_pe:
            pe_q = float((pe_series <= current_pe).mean())
        current_pb = market.get('pb')
        if pb_series is not None and current_pb:
            pb_q = float((pb_series <= current_pb).mean())

        from research.fundamental.scorer import ScorerInput
        fcf = (fin.get('operating_cashflow', 0) - fin.get('capex', 0))
        mv_yuan = (market.get('total_mv', 0) or 0) * 10_000
        fcf_yield = fcf / mv_yuan if mv_yuan > 0 else None

        scorer_input = ScorerInput(
            pe_quantile=pe_q,
            pb_quantile=pb_q,
            fcf_yield=fcf_yield,
            roe=fin.get('roe'),
            roe_prev=fin.get('roe_prev'),
            ocf_to_profit=fin.get('ocf_to_profit'),
            debt_ratio=(fin.get('total_liabilities', 0) / fin.get('total_assets', 1)
                        if fin.get('total_assets') else None),
            revenue_yoy=fin.get('revenue_yoy'),
            profit_yoy=fin.get('profit_yoy'),
        )
        score_result = self._scorer.score(scorer_input)

        # Expected return context
        try:
            exp_ret_str = self._tools.get_expected_return_context(code)
            # parse out the total return number from the string
            import re
            m = re.search(r'2年预期总回报[：:]\s*([\-\d.]+)%', exp_ret_str)
            expected_return_2yr = float(m.group(1)) / 100.0 if m else None
        except Exception:
            expected_return_2yr = None

        YI = 1_0000_0000
        return {
            'code': code,
            'snap_date': str(snap_date),
            'fundamental_score': score_result.composite_score,
            'pe_ttm': current_pe,
            'pe_quantile_5yr': round(pe_q, 3) if pe_q is not None else None,
            'pb': current_pb,
            'pb_quantile_5yr': round(pb_q, 3) if pb_q is not None else None,
            'roe': fin.get('roe'),
            'revenue_yoy': fin.get('revenue_yoy'),
            'profit_yoy': fin.get('profit_yoy'),
            'fcf': round(fcf / YI, 2) if fcf else None,
            'net_cash': None,
            'expected_return_2yr': round(expected_return_2yr, 4) if expected_return_2yr else None,
            'valuation_json': json.dumps(
                {'methods': val_result.methods, 'current_market_cap_yi': val_result.current_market_cap_yi},
                ensure_ascii=False,
            ),
        }

    def _upsert(self, row: dict) -> None:
        if execute_query is None:
            raise RuntimeError('config.db not available')
        execute_query(
            """INSERT INTO fundamental_snapshots
               (code, snap_date, fundamental_score, pe_ttm, pe_quantile_5yr,
                pb, pb_quantile_5yr, roe, revenue_yoy, profit_yoy,
                fcf, net_cash, expected_return_2yr, valuation_json)
               VALUES (%(code)s, %(snap_date)s, %(fundamental_score)s,
                       %(pe_ttm)s, %(pe_quantile_5yr)s, %(pb)s, %(pb_quantile_5yr)s,
                       %(roe)s, %(revenue_yoy)s, %(profit_yoy)s,
                       %(fcf)s, %(net_cash)s, %(expected_return_2yr)s, %(valuation_json)s)
               ON DUPLICATE KEY UPDATE
                 fundamental_score=VALUES(fundamental_score),
                 pe_ttm=VALUES(pe_ttm), pe_quantile_5yr=VALUES(pe_quantile_5yr),
                 pb=VALUES(pb), pb_quantile_5yr=VALUES(pb_quantile_5yr),
                 roe=VALUES(roe), revenue_yoy=VALUES(revenue_yoy),
                 profit_yoy=VALUES(profit_yoy), fcf=VALUES(fcf),
                 expected_return_2yr=VALUES(expected_return_2yr),
                 valuation_json=VALUES(valuation_json)""",
            row, env='online'
        )
```

Note: The `ON DUPLICATE KEY` upsert requires a unique key on `(code, snap_date)`. Add this to the migration or as a separate `ALTER TABLE` in the migration.

**Step 3: Run tests**
```bash
python -m pytest research/fundamental/tests/test_snapshot.py -v
```
Expected: 2 PASS

**Step 4: Commit**
```bash
git add research/fundamental/snapshot.py research/fundamental/tests/test_snapshot.py
git commit -m "feat(research): FundamentalSnapshot DB writer with upsert"
```

---

## Task 5: SentimentEventTracker — CRUD for sentiment_events

**Files:**
- Create: `research/sentiment/event_tracker.py`
- Create: `research/sentiment/tests/__init__.py`
- Create: `research/sentiment/tests/test_event_tracker.py`

**What it does:** Create/read/update/verify sentiment events. Called by API endpoints (manual entry) and future NLP pipeline.

**Step 1: Write tests**

```python
# research/sentiment/tests/test_event_tracker.py
# -*- coding: utf-8 -*-
import pytest
from unittest.mock import patch
from research.sentiment.event_tracker import SentimentEventTracker, EventRecord


def test_create_event_builds_valid_record():
    tracker = SentimentEventTracker.__new__(SentimentEventTracker)
    rec = tracker._build_record(
        code='300750', event_date='2026-04-05',
        event_text='实控人增持1亿元',
        direction='positive', magnitude='high',
        category='shareholder', source='公告'
    )
    assert rec['code'] == '300750'
    assert rec['direction'] == 'positive'
    assert rec['is_verified'] is False


def test_list_recent_returns_list(tmp_path):
    tracker = SentimentEventTracker.__new__(SentimentEventTracker)
    with patch('research.sentiment.event_tracker.execute_query', return_value=[
        {'id': 1, 'code': '300750', 'event_date': '2026-04-05',
         'event_text': 'test', 'direction': 'positive',
         'magnitude': 'high', 'category': 'shareholder',
         'is_verified': 0, 'verified_result': None, 'source': None}
    ]):
        rows = tracker.list_recent('300750', days=30)
    assert len(rows) == 1
    assert rows[0]['direction'] == 'positive'


def test_verify_event_updates_verified(tmp_path):
    tracker = SentimentEventTracker.__new__(SentimentEventTracker)
    with patch('research.sentiment.event_tracker.execute_query') as mock_eq:
        mock_eq.return_value = None
        tracker.verify(event_id=1, result='已兑现，股价上涨5%')
    mock_eq.assert_called_once()
    call_args = mock_eq.call_args[0]
    assert 'UPDATE sentiment_events' in call_args[0]
```

**Step 2: Implement `research/sentiment/event_tracker.py`**

```python
# -*- coding: utf-8 -*-
"""SentimentEventTracker — CRUD for sentiment_events table."""
import logging
from dataclasses import dataclass

logger = logging.getLogger('myTrader.research')

try:
    from config.db import execute_query
except ImportError:
    execute_query = None

VALID_DIRECTIONS = ('positive', 'negative', 'neutral')
VALID_MAGNITUDES = ('high', 'medium', 'low')
VALID_CATEGORIES = ('capital', 'earnings', 'policy', 'geopolitical',
                    'industry', 'technical', 'shareholder')


@dataclass
class EventRecord:
    code: str
    event_date: str
    event_text: str
    direction: str
    magnitude: str
    category: str
    source: str | None = None


class SentimentEventTracker:

    def create(self, code: str, event_date: str, event_text: str,
               direction: str, magnitude: str, category: str,
               source: str | None = None) -> int | None:
        """Insert a new event. Returns inserted id or None on failure."""
        if direction not in VALID_DIRECTIONS:
            raise ValueError(f'direction must be one of {VALID_DIRECTIONS}')
        if magnitude not in VALID_MAGNITUDES:
            raise ValueError(f'magnitude must be one of {VALID_MAGNITUDES}')
        if category not in VALID_CATEGORIES:
            raise ValueError(f'category must be one of {VALID_CATEGORIES}')

        rec = self._build_record(code, event_date, event_text,
                                  direction, magnitude, category, source)
        try:
            execute_query(
                """INSERT INTO sentiment_events
                   (code, event_date, event_text, direction, magnitude,
                    category, is_verified, source)
                   VALUES (%(code)s, %(event_date)s, %(event_text)s,
                           %(direction)s, %(magnitude)s, %(category)s,
                           %(is_verified)s, %(source)s)""",
                rec, env='online'
            )
            rows = execute_query('SELECT LAST_INSERT_ID() as id', env='online')
            return rows[0]['id'] if rows else None
        except Exception as e:
            logger.error('[EVENT_TRACKER] create failed: %s', e)
            return None

    def list_recent(self, code: str, days: int = 30) -> list[dict]:
        """Return events for code in the last `days` calendar days."""
        try:
            rows = execute_query(
                """SELECT id, code, event_date, event_text, direction,
                          magnitude, category, is_verified, verified_result, source
                   FROM sentiment_events
                   WHERE code = %s
                     AND event_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                   ORDER BY event_date DESC""",
                (code, days), env='online'
            )
            return rows or []
        except Exception as e:
            logger.error('[EVENT_TRACKER] list_recent failed: %s', e)
            return []

    def verify(self, event_id: int, result: str) -> None:
        """Mark an event as verified with outcome text."""
        try:
            execute_query(
                """UPDATE sentiment_events
                   SET is_verified = 1, verified_result = %s
                   WHERE id = %s""",
                (result, event_id), env='online'
            )
        except Exception as e:
            logger.error('[EVENT_TRACKER] verify failed: %s', e)

    def _build_record(self, code, event_date, event_text,
                      direction, magnitude, category, source=None) -> dict:
        return {
            'code': code,
            'event_date': event_date,
            'event_text': event_text[:300],
            'direction': direction,
            'magnitude': magnitude,
            'category': category,
            'is_verified': False,
            'source': source,
        }
```

**Step 3: Run tests + commit**
```bash
python -m pytest research/sentiment/tests/test_event_tracker.py -v
git add research/sentiment/ && git commit -m "feat(research): SentimentEventTracker CRUD"
```

---

## Task 6: SentimentScorer — 5-Dimension Scoring Engine

**Files:**
- Create: `research/sentiment/scorer.py`
- Create: `research/sentiment/tests/test_sentiment_scorer.py`

**Auto-computed dimensions** (from existing tech_scan data):
- `score_price_vol` (25%): RSI position + MACD histogram + volume ratio
- `score_sector` (20%): RPS rank + SW rotation position

**Manual/default dimensions** (default 50 = neutral):
- `score_fund` (30%): net money flow signal (manual or from future data)
- `score_consensus` (20%): analyst rating direction (manual)
- `score_macro` (5%): macro/geopolitical score (manual)

**Historical quantile:** once ≥60 records exist for code, compute `historical_quantile`.

**Step 1: Write tests**

```python
# research/sentiment/tests/test_sentiment_scorer.py
# -*- coding: utf-8 -*-
import pytest
from unittest.mock import patch, MagicMock
from research.sentiment.scorer import SentimentScorer, SentimentInput


def _make_input(**kwargs):
    defaults = dict(
        rsi=35.0, macd_hist=-0.5, vol_ratio=0.8,
        rps_120=55.0,
        score_fund=50, score_consensus=50, score_macro=50,
    )
    defaults.update(kwargs)
    return SentimentInput(**defaults)


def test_low_rsi_oversold_gives_higher_price_vol_score():
    inp_oversold = _make_input(rsi=25.0, macd_hist=-0.3, vol_ratio=0.5)
    inp_overbought = _make_input(rsi=80.0, macd_hist=0.8, vol_ratio=2.5)
    s = SentimentScorer()
    score_oversold = s._price_vol_score(inp_oversold)
    score_overbought = s._price_vol_score(inp_overbought)
    # oversold = bearish sentiment exhausted = higher score (buying opportunity signal)
    assert score_oversold > score_overbought


def test_composite_score_within_bounds():
    inp = _make_input()
    result = SentimentScorer().score(inp)
    assert 0 <= result.composite_score <= 100


def test_label_neutral_for_mid_scores():
    inp = _make_input(rsi=50.0, macd_hist=0.0, vol_ratio=1.0)
    result = SentimentScorer().score(inp)
    assert result.label in ('中性偏多', '中性', '中性偏空')


def test_historical_quantile_none_when_insufficient_history():
    inp = _make_input()
    scorer = SentimentScorer.__new__(SentimentScorer)
    with patch('research.sentiment.scorer.execute_query', return_value=[{'cnt': 5}]):
        quantile = scorer._compute_historical_quantile('300750', 65)
    assert quantile is None


def test_historical_quantile_computed_when_enough_history():
    inp = _make_input()
    scorer = SentimentScorer.__new__(SentimentScorer)
    with patch('research.sentiment.scorer.execute_query', side_effect=[
        [{'cnt': 80}],
        [{'pct': 0.72}],
    ]):
        quantile = scorer._compute_historical_quantile('300750', 65)
    assert quantile == pytest.approx(0.72)
```

**Step 2: Implement `research/sentiment/scorer.py`**

```python
# -*- coding: utf-8 -*-
"""SentimentScorer — 5-dimension sentiment scoring (auto + manual)."""
import logging
from dataclasses import dataclass, field

logger = logging.getLogger('myTrader.research')

try:
    from config.db import execute_query
except ImportError:
    execute_query = None

MIN_HISTORY_FOR_QUANTILE = 60

_LABELS = [
    (80, '强多'),
    (65, '中性偏多'),
    (50, '中性'),        # 45-55
    (35, '中性偏空'),
    (0,  '强空'),
]


@dataclass
class SentimentInput:
    # Auto-computable
    rsi: float | None = None            # 0..100
    macd_hist: float | None = None      # histogram value (positive/negative)
    vol_ratio: float | None = None      # current volume / 20d avg volume
    rps_120: float | None = None        # RPS 120-day rank 0..100
    # Manual / defaulted
    score_fund: int = 50                # capital flow score 0..100 (manual)
    score_consensus: int = 50           # analyst consensus 0..100 (manual)
    score_macro: int = 50               # macro/geo score 0..100 (manual)


@dataclass
class SentimentResult:
    composite_score: int
    score_fund: int
    score_price_vol: int
    score_consensus: int
    score_sector: int
    score_macro: int
    historical_quantile: float | None
    label: str


# Weights from design doc (individual stock)
W_FUND = 0.30
W_PRICE_VOL = 0.25
W_CONSENSUS = 0.20
W_SECTOR = 0.20
W_MACRO = 0.05


class SentimentScorer:

    def score(self, inp: SentimentInput, code: str | None = None) -> SentimentResult:
        pv = self._price_vol_score(inp)
        sec = self._sector_score(inp)

        composite = int(
            inp.score_fund * W_FUND +
            pv * W_PRICE_VOL +
            inp.score_consensus * W_CONSENSUS +
            sec * W_SECTOR +
            inp.score_macro * W_MACRO
        )
        composite = min(100, max(0, composite))

        historical_quantile = None
        if code:
            historical_quantile = self._compute_historical_quantile(code, composite)

        label = next(lbl for threshold, lbl in _LABELS if composite >= threshold)

        return SentimentResult(
            composite_score=composite,
            score_fund=inp.score_fund,
            score_price_vol=pv,
            score_consensus=inp.score_consensus,
            score_sector=sec,
            score_macro=inp.score_macro,
            historical_quantile=historical_quantile,
            label=label,
        )

    def _price_vol_score(self, inp: SentimentInput) -> int:
        """0..100. Low RSI (oversold) = sentiment exhaustion = higher score."""
        score = 50

        rsi = inp.rsi
        if rsi is not None:
            if rsi < 30:
                score += 20      # deeply oversold = panic = potential reversal
            elif rsi < 45:
                score += 10
            elif rsi > 70:
                score -= 20      # overbought = frothy = risk
            elif rsi > 60:
                score -= 10

        mh = inp.macd_hist
        if mh is not None:
            if mh > 0:
                score += 10      # positive histogram = momentum
            else:
                score -= 10

        vr = inp.vol_ratio
        if vr is not None:
            if vr > 2.0:
                score -= 5       # extreme volume on run-up = distribution risk
            elif vr < 0.5:
                score += 5       # low volume = no panic selling

        return min(100, max(0, score))

    def _sector_score(self, inp: SentimentInput) -> int:
        """0..100 based on RPS rank."""
        rps = inp.rps_120
        if rps is None:
            return 50
        # Linear: RPS 0 -> 10, RPS 50 -> 50, RPS 100 -> 90
        return min(100, max(0, int(rps * 0.8 + 10)))

    def _compute_historical_quantile(self, code: str, current_score: int) -> float | None:
        """Returns fraction 0..1 of historical scores <= current_score."""
        if execute_query is None:
            return None
        try:
            cnt_rows = execute_query(
                'SELECT COUNT(*) as cnt FROM sentiment_scores WHERE code=%s',
                (code,), env='online'
            )
            cnt = cnt_rows[0]['cnt'] if cnt_rows else 0
            if cnt < MIN_HISTORY_FOR_QUANTILE:
                return None
            pct_rows = execute_query(
                """SELECT COUNT(*) / %s as pct
                   FROM sentiment_scores
                   WHERE code=%s AND composite_score <= %s""",
                (cnt, code, current_score), env='online'
            )
            return float(pct_rows[0]['pct']) if pct_rows else None
        except Exception as e:
            logger.error('[SENTIMENT] _compute_historical_quantile failed: %s', e)
            return None
```

**Step 3: Run tests + commit**
```bash
python -m pytest research/sentiment/tests/test_sentiment_scorer.py -v
git add research/sentiment/scorer.py research/sentiment/tests/test_sentiment_scorer.py
git commit -m "feat(research): SentimentScorer 5-dimension auto+manual scoring"
```

---

## Task 7: CompositeAggregator + CrossSectionRules

**Files:**
- Create: `research/composite/aggregator.py`
- Create: `research/composite/rules.py`
- Create: `research/composite/tests/__init__.py`
- Create: `research/composite/tests/test_composite.py`

**Weights (from design doc):** technical×15% + fund_flow×20% + fundamental×30% + sentiment×15% + capital_cycle×20%

**Override rules** (from design doc section 3.3):
- phase 3 + fundamental > 70 → weight_boost 1.3 + signal "强多"
- phase 4 + pe_quantile > 0.8 → signal "强空" override=True
- phase 2 + sentiment < 45 → signal "等待布局"
- founder_reduce + technical_breakdown → signal "警戒" override=True

**Step 1: Write tests**

```python
# research/composite/tests/test_composite.py
# -*- coding: utf-8 -*-
import pytest
from research.composite.aggregator import CompositeAggregator, FiveSectionScores
from research.composite.rules import CrossSectionRules


def _make_scores(**kwargs):
    defaults = dict(
        score_technical=60, score_fund_flow=55,
        score_fundamental=70, score_sentiment=50,
        score_capital_cycle=65,
        pe_quantile=0.35, capital_cycle_phase=3,
        founder_reducing=False, technical_breakdown=False,
    )
    defaults.update(kwargs)
    return FiveSectionScores(**defaults)


def test_composite_score_uses_correct_weights():
    s = _make_scores(
        score_technical=100, score_fund_flow=100,
        score_fundamental=100, score_sentiment=100,
        score_capital_cycle=100,
    )
    result = CompositeAggregator().aggregate(s)
    assert result.composite_score == 100


def test_phase3_high_fundamental_boosts_score():
    base = _make_scores(score_fundamental=75, capital_cycle_phase=3)
    boosted_result = CompositeAggregator().aggregate(base)
    # Fundamental contribution boosted by 1.3
    assert boosted_result.direction in ('strong_bull', 'bull')


def test_phase4_high_pe_overrides_to_strong_bear():
    s = _make_scores(capital_cycle_phase=4, pe_quantile=0.85,
                     score_fundamental=80)
    result = CompositeAggregator().aggregate(s)
    assert result.direction == 'strong_bear'


def test_direction_enum_mapping():
    s_high = _make_scores(score_technical=90, score_fund_flow=85,
                           score_fundamental=88, score_sentiment=80,
                           score_capital_cycle=85)
    s_low = _make_scores(score_technical=20, score_fund_flow=25,
                          score_fundamental=20, score_sentiment=30,
                          score_capital_cycle=25)
    high = CompositeAggregator().aggregate(s_high)
    low = CompositeAggregator().aggregate(s_low)
    assert high.direction in ('strong_bull', 'bull')
    assert low.direction in ('strong_bear', 'bear')
```

**Step 2: Implement files**

`research/composite/rules.py`:
```python
# -*- coding: utf-8 -*-
"""CrossSectionRules — override and boost rules between the 5 sections."""
from dataclasses import dataclass

@dataclass
class RuleResult:
    override_direction: str | None = None   # if set, overrides computed direction
    fundamental_weight_boost: float = 1.0   # multiplier on fundamental score
    signal_note: str = ''


def apply_rules(phase: int, fundamental_score: int, pe_quantile: float,
                sentiment_score: int, founder_reducing: bool,
                technical_breakdown: bool) -> RuleResult:
    """Apply cross-section override rules per design doc section 3.3."""
    result = RuleResult()

    # phase 4 + pe_quantile > 0.8 = strong bear override
    if phase == 4 and pe_quantile > 0.80:
        result.override_direction = 'strong_bear'
        result.signal_note = '资本周期阶段4 + 估值历史高位，坚决不追'
        return result  # early return, highest priority

    # founder reducing + technical breakdown = 警戒 override
    if founder_reducing and technical_breakdown:
        result.override_direction = 'bear'
        result.signal_note = '创始人减持 + 技术面破位，降仓警戒'
        return result

    # phase 3 + fundamental > 70 = boost
    if phase == 3 and fundamental_score > 70:
        result.fundamental_weight_boost = 1.3
        result.signal_note = '资本周期阶段3 + 基本面高分，强买'

    # phase 2 + sentiment < 45 = wait for catalyst
    elif phase == 2 and sentiment_score < 45:
        result.signal_note = '资本周期阶段2 + 情绪低迷，等待催化布局'

    return result
```

`research/composite/aggregator.py`:
```python
# -*- coding: utf-8 -*-
"""CompositeAggregator — weighted 5-section score with cross-section rules."""
from dataclasses import dataclass

W_TECHNICAL = 0.15
W_FUND_FLOW = 0.20
W_FUNDAMENTAL = 0.30
W_SENTIMENT = 0.15
W_CAPITAL_CYCLE = 0.20

_DIRECTION_THRESHOLDS = [
    (75, 'strong_bull'),
    (60, 'bull'),
    (45, 'neutral'),
    (30, 'bear'),
    (0,  'strong_bear'),
]


@dataclass
class FiveSectionScores:
    score_technical: int = 50
    score_fund_flow: int = 50
    score_fundamental: int = 50
    score_sentiment: int = 50
    score_capital_cycle: int = 50
    pe_quantile: float = 0.5
    capital_cycle_phase: int = 0
    founder_reducing: bool = False
    technical_breakdown: bool = False


@dataclass
class AggregateResult:
    composite_score: int
    direction: str
    signal_note: str
    scores: FiveSectionScores


class CompositeAggregator:

    def aggregate(self, s: FiveSectionScores) -> AggregateResult:
        from research.composite.rules import apply_rules

        rule = apply_rules(
            phase=s.capital_cycle_phase,
            fundamental_score=s.score_fundamental,
            pe_quantile=s.pe_quantile,
            sentiment_score=s.score_sentiment,
            founder_reducing=s.founder_reducing,
            technical_breakdown=s.technical_breakdown,
        )

        boosted_fund = min(100, s.score_fundamental * rule.fundamental_weight_boost)

        composite = int(
            s.score_technical * W_TECHNICAL +
            s.score_fund_flow * W_FUND_FLOW +
            boosted_fund * W_FUNDAMENTAL +
            s.score_sentiment * W_SENTIMENT +
            s.score_capital_cycle * W_CAPITAL_CYCLE
        )
        composite = min(100, max(0, composite))

        if rule.override_direction:
            direction = rule.override_direction
        else:
            direction = next(d for threshold, d in _DIRECTION_THRESHOLDS
                             if composite >= threshold)

        return AggregateResult(
            composite_score=composite,
            direction=direction,
            signal_note=rule.signal_note,
            scores=s,
        )
```

**Step 3: Run tests + commit**
```bash
python -m pytest research/composite/tests/test_composite.py -v
git add research/composite/ && git commit -m "feat(research): CompositeAggregator + CrossSectionRules"
```

---

## Task 8: WatchlistManager — Company Pool CRUD

**Files:**
- Create: `research/watchlist/manager.py`
- Create: `research/watchlist/tests/__init__.py`
- Create: `research/watchlist/tests/test_watchlist.py`

**Step 1: Write tests**

```python
# research/watchlist/tests/test_watchlist.py
# -*- coding: utf-8 -*-
import pytest
from unittest.mock import patch
from research.watchlist.manager import WatchlistManager


def test_add_stock_builds_correct_insert():
    mgr = WatchlistManager.__new__(WatchlistManager)
    with patch('research.watchlist.manager.execute_query') as mock_eq:
        mock_eq.return_value = None
        mgr.add('300750', name='宁德时代', tier='deep', industry='锂电池')
    call_sql = mock_eq.call_args[0][0]
    assert 'INSERT INTO watchlist' in call_sql or 'REPLACE INTO watchlist' in call_sql


def test_upgrade_tier_calls_update():
    mgr = WatchlistManager.__new__(WatchlistManager)
    with patch('research.watchlist.manager.execute_query') as mock_eq:
        mock_eq.return_value = None
        mgr.set_tier('300750', 'standard')
    call_sql = mock_eq.call_args[0][0]
    assert 'UPDATE watchlist' in call_sql


def test_list_active_returns_list():
    mgr = WatchlistManager.__new__(WatchlistManager)
    with patch('research.watchlist.manager.execute_query', return_value=[
        {'id': 1, 'code': '300750', 'name': '宁德时代',
         'tier': 'deep', 'industry': '锂电池',
         'added_date': '2026-04-05', 'current_thesis': None,
         'is_active': 1}
    ]):
        rows = mgr.list_active()
    assert len(rows) == 1
    assert rows[0]['code'] == '300750'


def test_save_profile_yaml_updates_record():
    mgr = WatchlistManager.__new__(WatchlistManager)
    yaml_str = 'code: "300750"\nname: "宁德时代"'
    with patch('research.watchlist.manager.execute_query') as mock_eq:
        mock_eq.return_value = None
        mgr.save_profile('300750', yaml_str)
    call_args = mock_eq.call_args[0]
    assert 'profile_yaml' in call_args[0]
```

**Step 2: Implement `research/watchlist/manager.py`**

```python
# -*- coding: utf-8 -*-
"""WatchlistManager — manage the company tracking pool."""
import logging
from datetime import date

logger = logging.getLogger('myTrader.research')

try:
    from config.db import execute_query
except ImportError:
    execute_query = None

VALID_TIERS = ('deep', 'standard', 'watch')


class WatchlistManager:

    def add(self, code: str, name: str | None = None,
            tier: str = 'watch', industry: str | None = None,
            thesis: str | None = None) -> None:
        if tier not in VALID_TIERS:
            raise ValueError(f'tier must be one of {VALID_TIERS}')
        execute_query(
            """INSERT INTO watchlist (code, name, tier, industry, added_date, current_thesis, is_active)
               VALUES (%s, %s, %s, %s, %s, %s, 1)
               ON DUPLICATE KEY UPDATE
                 name=VALUES(name), tier=VALUES(tier),
                 industry=VALUES(industry), is_active=1""",
            (code, name, tier, industry, str(date.today()), thesis), env='online'
        )
        logger.info('[WATCHLIST] added %s (%s) as %s', code, name, tier)

    def remove(self, code: str) -> None:
        """Soft-delete (set is_active=0)."""
        execute_query(
            'UPDATE watchlist SET is_active=0 WHERE code=%s',
            (code,), env='online'
        )

    def set_tier(self, code: str, tier: str) -> None:
        if tier not in VALID_TIERS:
            raise ValueError(f'tier must be one of {VALID_TIERS}')
        execute_query(
            'UPDATE watchlist SET tier=%s WHERE code=%s',
            (tier, code), env='online'
        )

    def save_profile(self, code: str, yaml_str: str) -> None:
        execute_query(
            'UPDATE watchlist SET profile_yaml=%s WHERE code=%s',
            (yaml_str, code), env='online'
        )

    def update_thesis(self, code: str, thesis: str) -> None:
        execute_query(
            'UPDATE watchlist SET current_thesis=%s, thesis_updated_at=%s WHERE code=%s',
            (thesis[:200], str(date.today()), code), env='online'
        )

    def get(self, code: str) -> dict | None:
        rows = execute_query(
            'SELECT * FROM watchlist WHERE code=%s', (code,), env='online'
        )
        return rows[0] if rows else None

    def list_active(self, tier: str | None = None) -> list[dict]:
        if tier:
            rows = execute_query(
                'SELECT * FROM watchlist WHERE is_active=1 AND tier=%s ORDER BY tier, code',
                (tier,), env='online'
            )
        else:
            rows = execute_query(
                'SELECT * FROM watchlist WHERE is_active=1 ORDER BY tier, code',
                env='online'
            )
        return rows or []
```

**Step 3: Run tests + commit**
```bash
python -m pytest research/watchlist/tests/test_watchlist.py -v
git add research/watchlist/ && git commit -m "feat(research): WatchlistManager CRUD"
```

---

## Task 9: API Router `api/routers/research.py`

**Files:**
- Create: `api/routers/research.py`
- Modify: `api/main.py` (add `from api.routers import research` and `app.include_router(research.router)`)

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/research/fundamental/{code}` | Latest fundamental snapshot or compute on-demand |
| POST | `/api/research/fundamental/{code}/refresh` | Force re-compute and save snapshot |
| GET | `/api/research/valuation/{code}` | 8-method valuation (no DB write) |
| GET | `/api/research/sentiment/{code}/events` | List recent sentiment events |
| POST | `/api/research/sentiment/events` | Create sentiment event (manual entry) |
| PUT | `/api/research/sentiment/events/{event_id}/verify` | Mark event verified |
| GET | `/api/research/composite/{code}` | Latest composite score |
| POST | `/api/research/composite/{code}/compute` | Compute composite and save |
| GET | `/api/research/watchlist` | List all active watchlist stocks |
| POST | `/api/research/watchlist` | Add stock to watchlist |
| PUT | `/api/research/watchlist/{code}/tier` | Update tier |
| PUT | `/api/research/watchlist/{code}/thesis` | Update current thesis |
| DELETE | `/api/research/watchlist/{code}` | Soft-delete from watchlist |

**Step 1: Implement `api/routers/research.py`**

```python
# -*- coding: utf-8 -*-
"""Research router — five-section analysis endpoints."""
import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel

from api.middleware.auth import get_current_user
from api.models.user import User

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/research', tags=['research'])


# --------------------------------------------------------- Pydantic models
class CreateEventRequest(BaseModel):
    code: str
    event_date: str          # YYYY-MM-DD
    event_text: str
    direction: str           # positive / negative / neutral
    magnitude: str           # high / medium / low
    category: str
    source: str | None = None


class AddWatchlistRequest(BaseModel):
    code: str
    name: str | None = None
    tier: str = 'watch'
    industry: str | None = None
    thesis: str | None = None


class UpdateThesisRequest(BaseModel):
    thesis: str


class VerifyEventRequest(BaseModel):
    result: str


# --------------------------------------------------------- Fundamental
@router.get('/fundamental/{code}')
async def get_fundamental_snapshot(
    code: str,
    current_user: User = Depends(get_current_user),
):
    """Return latest fundamental snapshot from DB."""
    try:
        from config.db import execute_query
        rows = execute_query(
            'SELECT * FROM fundamental_snapshots WHERE code=%s ORDER BY snap_date DESC LIMIT 1',
            (code,), env='online'
        )
        if not rows:
            raise HTTPException(status_code=404, detail=f'No snapshot for {code}')
        import json
        row = dict(rows[0])
        if row.get('valuation_json') and isinstance(row['valuation_json'], str):
            row['valuation_json'] = json.loads(row['valuation_json'])
        return row
    except HTTPException:
        raise
    except Exception as e:
        logger.error('[RESEARCH] get_fundamental_snapshot failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/fundamental/{code}/refresh')
async def refresh_fundamental_snapshot(
    code: str,
    current_user: User = Depends(get_current_user),
):
    """Force recompute and persist fundamental snapshot."""
    try:
        from research.fundamental.snapshot import FundamentalSnapshot
        snap = FundamentalSnapshot()
        row = snap.save(code)
        return {'message': f'Snapshot refreshed for {code}', 'snap_date': row['snap_date'],
                'fundamental_score': row['fundamental_score']}
    except Exception as e:
        logger.error('[RESEARCH] refresh_fundamental_snapshot failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/valuation/{code}')
async def get_valuation(
    code: str,
    dcf_growth1: float = Query(default=0.15, ge=0.0, le=1.0),
    dcf_growth2: float = Query(default=0.08, ge=0.0, le=1.0),
    current_user: User = Depends(get_current_user),
):
    """Return 8-method valuation result (not persisted)."""
    try:
        from research.fundamental.valuation import FundamentalValuator
        v = FundamentalValuator()
        result = v.compute(code, dcf_growth1=dcf_growth1, dcf_growth2=dcf_growth2)
        return {
            'code': result.code,
            'current_market_cap_yi': result.current_market_cap_yi,
            'methods': result.methods,
            'notes': result.notes,
        }
    except Exception as e:
        logger.error('[RESEARCH] get_valuation failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


# --------------------------------------------------------- Sentiment
@router.get('/sentiment/{code}/events')
async def list_sentiment_events(
    code: str,
    days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
):
    try:
        from research.sentiment.event_tracker import SentimentEventTracker
        tracker = SentimentEventTracker()
        return {'code': code, 'events': tracker.list_recent(code, days=days)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/sentiment/events')
async def create_sentiment_event(
    body: CreateEventRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        from research.sentiment.event_tracker import SentimentEventTracker
        tracker = SentimentEventTracker()
        event_id = tracker.create(
            code=body.code, event_date=body.event_date,
            event_text=body.event_text, direction=body.direction,
            magnitude=body.magnitude, category=body.category,
            source=body.source,
        )
        return {'message': 'Event created', 'id': event_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put('/sentiment/events/{event_id}/verify')
async def verify_sentiment_event(
    event_id: int,
    body: VerifyEventRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        from research.sentiment.event_tracker import SentimentEventTracker
        SentimentEventTracker().verify(event_id, body.result)
        return {'message': 'Event verified'}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --------------------------------------------------------- Composite
@router.get('/composite/{code}')
async def get_composite_score(
    code: str,
    current_user: User = Depends(get_current_user),
):
    """Return latest composite score from DB."""
    try:
        from config.db import execute_query
        rows = execute_query(
            'SELECT * FROM composite_scores WHERE code=%s ORDER BY score_date DESC LIMIT 1',
            (code,), env='online'
        )
        if not rows:
            raise HTTPException(status_code=404, detail=f'No composite score for {code}')
        return dict(rows[0])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/composite/{code}/compute')
async def compute_composite_score(
    code: str,
    score_technical: int = Query(default=50, ge=0, le=100),
    score_fund_flow: int = Query(default=50, ge=0, le=100),
    score_sentiment: int = Query(default=50, ge=0, le=100),
    score_capital_cycle: int = Query(default=50, ge=0, le=100),
    capital_cycle_phase: int = Query(default=0, ge=0, le=5),
    current_user: User = Depends(get_current_user),
):
    """Compute composite score using latest fundamental + provided section scores."""
    try:
        from config.db import execute_query
        from research.composite.aggregator import CompositeAggregator, FiveSectionScores

        # Fetch latest fundamental score
        rows = execute_query(
            'SELECT fundamental_score, pe_quantile_5yr FROM fundamental_snapshots '
            'WHERE code=%s ORDER BY snap_date DESC LIMIT 1',
            (code,), env='online'
        )
        fund_score = rows[0]['fundamental_score'] if rows else 50
        pe_q = float(rows[0]['pe_quantile_5yr'] or 0.5) if rows else 0.5

        scores = FiveSectionScores(
            score_technical=score_technical,
            score_fund_flow=score_fund_flow,
            score_fundamental=fund_score,
            score_sentiment=score_sentiment,
            score_capital_cycle=score_capital_cycle,
            pe_quantile=pe_q,
            capital_cycle_phase=capital_cycle_phase,
        )
        result = CompositeAggregator().aggregate(scores)

        # Persist
        execute_query(
            """INSERT INTO composite_scores
               (code, score_date, score_technical, score_fund_flow,
                score_fundamental, score_sentiment, score_capital_cycle,
                composite_score, direction, phase, key_signal)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (code, str(date.today()), score_technical, score_fund_flow,
             fund_score, score_sentiment, score_capital_cycle,
             result.composite_score, result.direction,
             capital_cycle_phase, result.signal_note),
            env='online'
        )

        return {
            'code': code,
            'composite_score': result.composite_score,
            'direction': result.direction,
            'signal_note': result.signal_note,
            'section_scores': {
                'technical': score_technical,
                'fund_flow': score_fund_flow,
                'fundamental': fund_score,
                'sentiment': score_sentiment,
                'capital_cycle': score_capital_cycle,
            }
        }
    except Exception as e:
        logger.error('[RESEARCH] compute_composite failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


# --------------------------------------------------------- Watchlist
@router.get('/watchlist')
async def list_watchlist(
    tier: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
):
    try:
        from research.watchlist.manager import WatchlistManager
        return {'watchlist': WatchlistManager().list_active(tier=tier)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/watchlist')
async def add_to_watchlist(
    body: AddWatchlistRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        from research.watchlist.manager import WatchlistManager
        WatchlistManager().add(body.code, body.name, body.tier,
                                body.industry, body.thesis)
        return {'message': f'{body.code} added to watchlist'}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put('/watchlist/{code}/tier')
async def update_watchlist_tier(
    code: str,
    tier: str = Query(..., pattern='^(deep|standard|watch)$'),
    current_user: User = Depends(get_current_user),
):
    try:
        from research.watchlist.manager import WatchlistManager
        WatchlistManager().set_tier(code, tier)
        return {'message': f'{code} tier updated to {tier}'}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put('/watchlist/{code}/thesis')
async def update_thesis(
    code: str,
    body: UpdateThesisRequest,
    current_user: User = Depends(get_current_user),
):
    try:
        from research.watchlist.manager import WatchlistManager
        WatchlistManager().update_thesis(code, body.thesis)
        return {'message': f'Thesis updated for {code}'}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete('/watchlist/{code}')
async def remove_from_watchlist(
    code: str,
    current_user: User = Depends(get_current_user),
):
    try:
        from research.watchlist.manager import WatchlistManager
        WatchlistManager().remove(code)
        return {'message': f'{code} removed from watchlist'}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

**Step 2: Register router in `api/main.py`**

Add to the existing router imports:
```python
from api.routers import health, auth, market, analysis, strategy, rag, portfolio, admin, api_keys, subscription, research
```

Add after `app.include_router(subscription.router)`:
```python
app.include_router(research.router)
```

**Step 3: Syntax check + commit**
```bash
python -c "
import ast
for f in ['api/routers/research.py', 'api/main.py']:
    ast.parse(open(f).read())
    print('OK', f)
"
git add api/routers/research.py api/main.py
git commit -m "feat(api): add research router with 13 five-section endpoints"
```

---

## Task 10: Full Test Suite Run + Final Commit

**Step 1: Run full suite**
```bash
python -m pytest research/ investment_rag/tests/ scheduler/tests/ \
  --ignore=investment_rag/tests/test_store.py -v 2>&1 | tail -20
```
Expected: all PASS (new research tests + existing 150)

**Step 2: Syntax check migration**
```bash
python -c "import ast; ast.parse(open('alembic/versions/a1b2c3d4e5f6_research_tables.py').read()); print('OK')"
```

**Step 3: Final commit**
```bash
git add -A
git commit -m "feat(research): complete five-section framework Phase 1-3

- Task 0: Alembic migration for 5 research tables
- Task 1: research/ package structure
- Task 2: FundamentalValuator 8-method valuation
- Task 3: FundamentalScorer 0-100 earnings/valuation/growth
- Task 4: FundamentalSnapshot DB weekly writer
- Task 5: SentimentEventTracker CRUD
- Task 6: SentimentScorer 5-dimension auto+manual
- Task 7: CompositeAggregator + CrossSectionRules
- Task 8: WatchlistManager company pool CRUD
- Task 9: api/routers/research.py 13 endpoints"
```

---

## Summary

| Task | Files Created | Tests |
|------|-------------|-------|
| T0: DB Migration | `alembic/versions/a1b2c3d4e5f6_*.py` | syntax check |
| T1: Package structure | 5x `__init__.py` | import check |
| T2: FundamentalValuator | `research/fundamental/valuation.py` | 5 tests |
| T3: FundamentalScorer | `research/fundamental/scorer.py` | 5 tests |
| T4: FundamentalSnapshot | `research/fundamental/snapshot.py` | 2 tests |
| T5: SentimentEventTracker | `research/sentiment/event_tracker.py` | 3 tests |
| T6: SentimentScorer | `research/sentiment/scorer.py` | 4 tests |
| T7: CompositeAggregator | `research/composite/aggregator.py` + `rules.py` | 4 tests |
| T8: WatchlistManager | `research/watchlist/manager.py` | 4 tests |
| T9: API Router | `api/routers/research.py` + `api/main.py` | syntax check |
| T10: Integration | — | full suite |

**Total new tests: ~27 | Total new files: ~20**
