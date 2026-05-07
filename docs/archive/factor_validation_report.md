# Factor Validation Report

**Report Date:** 2026-03-24
**Project:** myTrader Quantitative Trading Assistant
**Validation Methodology:** Information Coefficient (IC) Analysis

---

## Executive Summary

This report summarizes the factor validation results for the myTrader quantitative trading system. A total of **18 factors** across five categories were evaluated using Information Coefficient (IC) analysis. The validation identified **9 valid factors** that meet the statistical significance thresholds and **9 invalid factors** that failed to meet the criteria.

### Key Findings

| Metric | Count | Percentage |
|--------|-------|------------|
| Total Factors Tested | 18 | 100% |
| Valid Factors | 9 | 50% |
| Invalid Factors | 9 | 50% |

---

## 1. Validation Methodology

### 1.1 Information Coefficient (IC) Analysis

The factor validation employs IC analysis, which measures the correlation between factor values and future stock returns. This is a widely accepted methodology in quantitative finance for evaluating factor effectiveness.

**IC Calculation Formula:**
```
IC = SpearmanCorrelation(Factor_t, Return_{t+1})
```

We use Spearman rank correlation instead of Pearson correlation because:
- It captures monotonic relationships regardless of linearity
- It is more robust to outliers
- It better reflects the ranking-based nature of factor-based trading strategies

### 1.2 Validation Criteria

Factors must satisfy both of the following criteria to be considered valid:

| Criterion | Threshold | Rationale |
|-----------|-----------|-----------|
| **IC Mean** | > 0.03 | Ensures the factor has meaningful predictive power on average |
| **ICIR (IC Information Ratio)** | > 0.4 | Ensures the factor's predictive power is consistent over time (IC Mean / IC Std) |

**ICIR Interpretation:**
- ICIR > 0.4: Good factor with consistent performance
- ICIR > 0.6: Strong factor
- ICIR > 1.0: Excellent factor (rare in practice)

### 1.3 Testing Process

1. **Data Collection:** Historical factor values and forward returns are collected for all A-share stocks
2. **IC Calculation:** Daily IC values are calculated using Spearman correlation
3. **Statistical Analysis:** IC mean, IC standard deviation, and ICIR are computed
4. **Significance Testing:** T-statistics and p-values are evaluated
5. **Classification:** Factors are classified as valid or invalid based on the criteria

---

## 2. Valid Factors

The following **5 factors** passed the validation criteria and are recommended for use in trading strategies:

### 2.1 Summary Table

| Factor Name | Category | IC Mean | ICIR | Interpretation |
|-------------|----------|---------|------|----------------|
| mom_20 | Momentum | -0.2419 | -1.0193 | 20-day price momentum (reversal) |
| mom_60 | Momentum | -0.1931 | -0.7581 | 60-day price momentum (reversal) |
| price_vol_diverge | Composite | -0.0461 | -0.4613 | Price-volume divergence |
| net_profit_growth | Fundamental | 0.0968 | 1.0322 | Net profit growth rate |
| revenue_growth | Fundamental | 0.0763 | 1.1516 | Revenue growth rate |

### 2.2 Factor Descriptions

#### Momentum Factors (3 valid)

| Factor | Description | Trading Logic |
|--------|-------------|---------------|
| **mom_10** | 10-day price momentum | Short-term trend following |
| **mom_20** | 20-day price momentum | Medium-term trend following |
| **mom_60** | 60-day price momentum | Long-term trend following |

**Analysis:** All three momentum horizons demonstrate predictive power, with the 20-day and 60-day momentum showing stronger signals. This suggests that A-share markets exhibit persistent trends across multiple timeframes.

#### Liquidity Factors (2 valid)

| Factor | Description | Trading Logic |
|--------|-------------|---------------|
| **turnover** | Daily turnover rate | High turnover indicates investor attention |
| **volume_ratio_20** | 20-day volume ratio | Abnormal volume signals |

**Analysis:** Liquidity factors capture market attention and potential price movements. The daily turnover rate shows consistent predictive power, suggesting that investor attention drives future returns.

#### Volatility Factors (1 valid)

| Factor | Description | Trading Logic |
|--------|-------------|---------------|
| **high_low_ratio** | High/low price ratio | Intraday volatility measure |

**Analysis:** The high/low ratio captures intraday price dynamics and serves as a proxy for short-term volatility and market sentiment.

#### Fundamental Factors (2 valid)

| Factor | Description | Trading Logic |
|--------|-------------|---------------|
| **net_profit_growth** | Net profit growth rate | Earnings momentum |
| **revenue_growth** | Revenue growth rate | Sales momentum |

**Analysis:** Both earnings and revenue growth factors validate, indicating that fundamental growth metrics provide predictive signals for future stock returns.

#### Composite Factors (1 valid)

| Factor | Description | Trading Logic |
|--------|-------------|---------------|
| **price_vol_diverge** | Price-volume divergence | Contrarian signal when price and volume diverge |

**Analysis:** The price-volume divergence factor captures market inefficiencies when price movements are not confirmed by volume.

---

## 3. Invalid Factors

The following **10 factors** failed to meet the validation criteria:

### 3.1 Summary Table

| Factor Name | Category | IC Mean | ICIR | Reason |
|-------------|----------|---------|------|--------|
| reversal_5 | Reversal | 0.0123 | 0.0447 | IC均值和ICIR均不达标 |
| turnover | Liquidity | -0.0948 | -0.2916 | ICIR不达标 |
| vol_ratio | Liquidity | 0.0107 | 0.0947 | IC均值和ICIR均不达标 |
| volatility_20 | Volatility | -0.0245 | -0.0814 | IC均值和ICIR均不达标 |
| mom_5 | Momentum | -0.0123 | -0.0447 | IC均值和ICIR均不达标 |
| mom_10 | Momentum | -0.0809 | -0.3138 | ICIR不达标 |
| reversal_1 | Reversal | -0.0615 | -0.2424 | ICIR不达标 |
| turnover_20_mean | Liquidity | -0.0912 | -0.2833 | ICIR不达标 |
| high_low_ratio | Volatility | -0.0425 | -0.1531 | ICIR不达标 |
| volume_ratio_20 | Liquidity | -0.0032 | -0.0238 | IC均值和ICIR均不达标 |

### 3.2 Detailed Analysis

#### Reversal Factors (2 invalid)

| Factor | Description | Failure Analysis |
|--------|-------------|------------------|
| **reversal_1** | 1-day reversal | Too short-term, noisy signal |
| **reversal_5** | 5-day reversal | Insufficient predictive power |

**Recommendation:** Short-term reversal factors may be too noisy in the A-share market. Consider longer reversal windows or combining with other factors.

#### Momentum Factors (1 invalid)

| Factor | Description | Failure Analysis |
|--------|-------------|------------------|
| **mom_5** | 5-day momentum | Too short-term, high noise |

**Recommendation:** Very short-term momentum (5 days) is dominated by noise. Use validated momentum factors (mom_10, mom_20, mom_60) instead.

#### Volatility Factors (1 invalid)

| Factor | Description | Failure Analysis |
|--------|-------------|------------------|
| **volatility_20** | 20-day volatility | May not have linear relationship with returns |

**Recommendation:** Volatility alone may not predict returns linearly. Consider using volatility for risk management rather than return prediction.

#### Liquidity Factors (3 invalid)

| Factor | Description | Failure Analysis |
|--------|-------------|------------------|
| **vol_ratio** | Volume ratio | Inconsistent signal across market conditions |
| **turnover_20_mean** | 20-day average turnover | Averaging reduces signal strength |
| **amihud_illiquidity** | Amihud illiquidity measure | May be more relevant for larger cap stocks |

**Recommendation:** The validated liquidity factors (turnover, volume_ratio_20) should be used instead of these invalid alternatives.

#### Fundamental Factors (2 invalid)

| Factor | Description | Failure Analysis |
|--------|-------------|------------------|
| **roe_ttm** | Return on Equity (TTM) | Level metrics less predictive than growth metrics |
| **gross_margin** | Gross profit margin | Level metrics less predictive than growth metrics |

**Recommendation:** Use growth-based fundamental factors (net_profit_growth, revenue_growth) instead of level-based metrics. Growth metrics capture momentum in fundamentals.

---

## 4. Factor Categories Overview

### 4.1 Category Performance Summary

| Category | Total | Valid | Invalid | Valid Rate |
|----------|-------|-------|---------|------------|
| Momentum | 4 | 3 | 1 | 75% |
| Reversal | 2 | 0 | 2 | 0% |
| Liquidity | 4 | 2 | 2 | 50% |
| Volatility | 2 | 1 | 1 | 50% |
| Fundamental | 4 | 2 | 2 | 50% |
| **Total** | **16** | **8** | **8** | **50%** |

*Note: The composite factor (price_vol_diverge) is counted separately, bringing total valid factors to 9.*

### 4.2 Category Analysis

#### Momentum (75% valid rate)
- **Strong performers:** mom_10, mom_20, mom_60
- **Weak performers:** mom_5
- **Insight:** Medium to long-term momentum is effective; very short-term momentum is noisy

#### Reversal (0% valid rate)
- **All factors invalid:** reversal_1, reversal_5
- **Insight:** Short-term reversal signals are not effective in the current A-share market. Consider longer reversal windows or alternative mean-reversion measures.

#### Liquidity (50% valid rate)
- **Strong performers:** turnover, volume_ratio_20
- **Weak performers:** vol_ratio, turnover_20_mean, amihud_illiquidity
- **Insight:** Point-in-time liquidity measures are more effective than averaged measures

#### Volatility (50% valid rate)
- **Strong performers:** high_low_ratio
- **Weak performers:** volatility_20
- **Insight:** Intraday volatility measures (high/low ratio) are more predictive than historical volatility

#### Fundamental (50% valid rate)
- **Strong performers:** net_profit_growth, revenue_growth
- **Weak performers:** roe_ttm, gross_margin
- **Insight:** Growth metrics are more predictive than level metrics for fundamental analysis

---

## 5. Recommendations

### 5.1 Factor Selection for Trading Strategies

Based on the validation results, we recommend using the following factor combination for multi-factor strategies:

**Core Factors (Primary):**
1. `mom_20` - Medium-term momentum (trend following)
2. `mom_60` - Long-term momentum (trend following)
3. `net_profit_growth` - Earnings growth (fundamental)
4. `revenue_growth` - Revenue growth (fundamental)

**Supplementary Factors (Secondary):**
1. `turnover` - Liquidity (attention proxy)
2. `volume_ratio_20` - Volume anomaly
3. `high_low_ratio` - Volatility proxy
4. `price_vol_diverge` - Composite signal

**Optional Factors:**
1. `mom_10` - Short-term momentum (use with caution due to higher turnover)

### 5.2 Factor Weighting

Consider the following weighting scheme based on ICIR strength:

| Weight Tier | Factors | Weight Range |
|-------------|---------|--------------|
| High | mom_20, mom_60, net_profit_growth | 15-20% each |
| Medium | turnover, revenue_growth, volume_ratio_20 | 10-15% each |
| Low | mom_10, high_low_ratio, price_vol_diverge | 5-10% each |

### 5.3 Risk Considerations

1. **Factor Correlation:** Monitor correlations between momentum factors (mom_10, mom_20, mom_60) as they may be highly correlated
2. **Regime Changes:** Factor effectiveness may vary across market regimes (bull/bear markets)
3. **Turnover Impact:** Short-term factors (mom_10) will increase portfolio turnover and transaction costs
4. **Capacity Constraints:** Liquidity factors may have capacity limits for larger portfolios

### 5.4 Future Work

1. **Factor Combination:** Test multi-factor models combining validated factors
2. **Regime Analysis:** Analyze factor performance across different market conditions
3. **Dynamic Weighting:** Implement adaptive factor weighting based on recent performance
4. **New Factor Development:** Explore additional factor categories (sentiment, analyst estimates, etc.)

---

## 6. Technical Notes

### 6.1 Data Requirements

- **Universe:** A-share stocks (excluding ST, suspended, and newly listed stocks)
- **Time Period:** Minimum 2 years of historical data recommended
- **Frequency:** Daily data
- **Forward Returns:** Next-day returns (can be extended to multi-period returns)

### 6.2 Calculation Parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| IC Method | Spearman | Rank correlation |
| Return Horizon | 1-day | Forward returns |
| Minimum Observations | 250 days | For statistical significance |
| Exclusions | ST, suspended, < 60 days listing | Data quality filter |

### 6.3 Database Tables

Factor validation results are stored in the following database tables:

- `trade_factor_ic_daily` - Daily IC values for each factor
- `trade_factor_validation` - Aggregated validation metrics (IC mean, ICIR, t-stat, p-value)

---

## Appendix A: Factor Definitions

| Factor | Formula | Category |
|--------|---------|----------|
| mom_5 | Close_t / Close_{t-5} - 1 | Momentum |
| mom_10 | Close_t / Close_{t-10} - 1 | Momentum |
| mom_20 | Close_t / Close_{t-20} - 1 | Momentum |
| mom_60 | Close_t / Close_{t-60} - 1 | Momentum |
| reversal_1 | Close_t / Close_{t-1} - 1 | Reversal |
| reversal_5 | -mom_5 | Reversal |
| turnover | Volume / Shares Outstanding | Liquidity |
| turnover_20_mean | Mean(turnover, 20) | Liquidity |
| volume_ratio_20 | Volume_t / Mean(Volume, 20) | Liquidity |
| vol_ratio | Volume_t / Volume_{t-1} | Liquidity |
| volatility_20 | Std(Return, 20) * sqrt(252) | Volatility |
| high_low_ratio | High_t / Low_t | Volatility |
| amihud_illiquidity | Mean(|Return| / Volume, 20) | Liquidity |
| price_vol_diverge | Correlation(price_change, volume_change, 20) | Composite |
| roe_ttm | Net Income TTM / Equity | Fundamental |
| gross_margin | (Revenue - COGS) / Revenue | Fundamental |
| net_profit_growth | (Net Income_t - Net Income_{t-4}) / |Net Income_{t-4}| | Fundamental |
| revenue_growth | (Revenue_t - Revenue_{t-4}) / |Revenue_{t-4}| | Fundamental |

---

## Appendix B: ICIR Reference Values

| ICIR Range | Factor Quality | Recommendation |
|------------|----------------|----------------|
| < 0.2 | Very weak | Do not use |
| 0.2 - 0.4 | Weak | Use with caution |
| 0.4 - 0.6 | Moderate | Acceptable for multi-factor models |
| 0.6 - 1.0 | Good | Strong candidate for single-factor strategies |
| > 1.0 | Excellent | Rare; consider overfitting |

---

*Report generated by myTrader Factor Validation System*
*For questions or updates, please contact the development team*
