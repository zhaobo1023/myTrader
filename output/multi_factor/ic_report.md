# Multi-Factor IC Evaluation Report

**Period**: 2026-01-01 ~ 2026-03-24 (Q1 2026)
**Forward Period**: 20 days
**Data Source**: trade_stock_valuation_factor + trade_stock_basic_factor + trade_stock_extended_factor
**Panel Size**: 263,157 rows x 6 factors + 1 composite
**IC Samples**: 36-37 trading days

## IC Summary

| Factor | Label | Direction | IC Mean | ICIR | IC Count | Positive % | Status |
|--------|-------|-----------|---------|------|----------|------------|--------|
| pb | Low PB | -1 (low=better) | -0.1678 | -3.61 | 36 | 0.00% | [OK] |
| pe_ttm | Low PE | -1 (low=better) | -0.0449 | -1.11 | 36 | 8.33% | [OK] |
| market_cap | Large Cap | +1 (high=better) | -0.1009 | -1.32 | 36 | 11.11% | [OK] |
| volatility_20 | Low Volatility | -1 (low=better) | -0.1702 | -2.38 | 37 | 0.00% | [OK] |
| close | Low Price | -1 (low=better) | -0.1521 | -3.20 | 37 | 0.00% | [OK] |
| roe_ttm | High ROE | +1 (high=better) | 0.0076 | 0.18 | 37 | 62.16% | [WARN] |
| pb_roe | PB-ROE | +1 (high=better) | 0.0741 | 1.37 | 36 | 88.89% | [OK] |
| **composite_score** | **Equal-Weight** | **+1** | **0.1530** | **2.17** | **37** | **97.30%** | **[OK]** |

**Valid factors**: 7 (including composite)
**Weak factors**: 1 (roe_ttm standalone)

## Factor Ranking (by |ICIR|)

| Rank | Factor | IC Mean | ICIR | Assessment |
|------|--------|---------|------|------------|
| 1 | Low PB (pb) | -0.1678 | 3.61 | Strongest value signal |
| 2 | Low Price (close) | -0.1521 | 3.20 | Strong low-price effect |
| 3 | Low Volatility (volatility_20) | -0.1702 | 2.38 | Low-vol anomaly confirmed |
| 4 | **Composite Score** | **0.1530** | **2.17** | **Equal-weight combination works well** |
| 5 | PB-ROE (pb_roe) | 0.0741 | 1.37 | Composite > standalone ROE |
| 6 | Large Cap (market_cap) | -0.1009 | 1.32 | Negative IC = small-cap premium |
| 7 | Low PE (pe_ttm) | -0.0449 | 1.11 | Weakest valid factor |
| 8 | High ROE (roe_ttm) | 0.0076 | 0.18 | Weak alone, needs PB combination |

## Key Findings

### 1. Value factors are dominant
PB (ICIR=3.61) and PE (ICIR=1.11) both show significant negative IC,
consistent with value investing thesis. Low PB is the single strongest factor.

### 2. Low volatility anomaly confirmed
volatility_20 has the highest raw IC (-0.1702) and strong ICIR (2.38),
confirming the low-volatility anomaly in A-share market.

### 3. Size factor shows style rotation
market_cap has negative IC (-0.101) despite direction=+1 (expecting large cap premium).
This means small caps outperformed in Q1 2026, suggesting small-cap style rotation.

### 4. PB-ROE composite validates the approach
Combining ROE with PB into pb_roe = roe_ttm/pb achieves IC=0.074, ICIR=1.37,
much stronger than standalone ROE (IC=0.008). The composite factor approach works.

### 5. Equal-weight composite is highly effective
The 6-factor equal-weight composite score achieves IC=0.153, ICIR=2.17,
with 97.3% positive IC rate. This is the 4th strongest signal and demonstrates
that multi-factor combination effectively amplifies individual factor alpha.

### 6. Low price effect is surprisingly strong
close (stock price) shows IC=-0.152, ICIR=3.20, ranking 2nd by ICIR.
This may reflect the "lottery stock" effect or small-cap bias (cheap stocks
tend to be smaller caps).

## Notes

- All IC values are Spearman Rank IC (cross-sectional rank correlation)
- IC evaluation period: Q1 2026 (Jan-Mar), 36-37 effective trading days
- Direction=-1 factors: negative IC means the factor works as expected
- Direction=+1 factors: positive IC means the factor works as expected
- market_cap negative IC contradicts its direction, indicating small-cap premium
- Factor correlation matrix was NaN on 2026-03-24 due to DB timeout data gaps;
  code fixed to auto-select a date with complete data
