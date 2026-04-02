# Multi-Factor Stock Selector Design

## Overview

Build a multi-factor stock selection framework for defensive/value style investing. Step 1 uses 6 existing factors, no new data required.

## Module Structure

```
strategist/multi_factor/
├── __init__.py
├── config.py          # Factor definitions, directions, weights
├── data_loader.py     # Merge factor data from 4 DB tables
├── scorer.py          # FactorSelector: percentile scoring + composite + select
├── evaluator.py       # IC evaluation (reuse Spearman IC logic)
└── run_selector.py    # CLI entry point
```

## Factors (Step 1)

| Factor       | Source Table                    | Field         | Direction | Rationale         |
|-------------|---------------------------------|---------------|-----------|-------------------|
| pb          | trade_stock_valuation_factor    | pb            | -1 (low)  | Low PB ranking #1 |
| pe_ttm      | trade_stock_valuation_factor    | pe_ttm        | -1 (low)  | Low PE ranking #8 |
| market_cap  | trade_stock_valuation_factor    | market_cap    | +1 (high) | Large cap ranking #7 |
| volatility_20 | trade_stock_basic_factor      | volatility_20 | -1 (low)  | Low vol ranking #3 |
| close       | trade_stock_basic_factor        | close         | -1 (low)  | Low price ranking #4 |
| roe_ttm     | trade_stock_extended_factor     | roe_ttm       | +1 (high) | Quality ranking #6 |

## Scoring Logic

Cross-sectional percentile ranking per factor, direction-aware, then equal-weight composite.

## Reusable Components

- `data_analyst/factors/factor_validator.py`: IC calculation (calculate_ic_series, validate_factor)
- `strategist/xgboost_strategy/preprocessor.py`: MAD + Z-Score (optional)

## Output

- CSV: selected stocks per rebalance date
- Markdown report: IC summary + backtest performance
- No new DB tables (Step 1)

## CLI

```bash
python -m strategist.multi_factor.run_selector --mode ic --start 2024-01-01
python -m strategist.multi_factor.run_selector --mode select --top-n 50 --date 2026-03-24
python -m strategist.multi_factor.run_selector --mode backtest --start 2024-01-01 --top-n 50
```

## Not in Scope (YAGNI)

- No industry neutralization
- No factor orthogonality/PCA
- No new DB tables
- No real-time scheduling
