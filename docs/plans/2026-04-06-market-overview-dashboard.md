# Market Overview Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a market overview dashboard at `/market` showing macro-timing, style rotation, and dividend tracking indicators with signals and explanations.

**Architecture:** Extend existing `macro_data` table (date/indicator/value) with 13 new indicators fetched via AKShare; new `market_overview` module computes derived signals; single FastAPI endpoint `/api/market-overview/summary` with 6h Redis cache; frontend rewrites the existing `/market` page using lightweight-charts for time series and Tailwind cards for stats.

**Tech Stack:** Python/AKShare (data), FastAPI + Redis cache (API), Next.js 16 + lightweight-charts v5 + Tailwind v4 (frontend)

---

## Indicator Map

| Key in macro_data | Name | AKShare call | Frequency |
|---|---|---|---|
| `idx_all_a` | 中证全A | `index_zh_a_hist('000985')` | daily |
| `idx_csi300` | 沪深300 | `index_zh_a_hist('000300')` | daily |
| `idx_csi500` | 中证500 | `index_zh_a_hist('000905')` | daily |
| `idx_csi1000` | 中证1000 | `index_zh_a_hist('000852')` | daily |
| `idx_dividend` | 中证红利 | `index_zh_a_hist('000922')` | daily |
| `idx_growth300` | 沪深300成长 | `index_zh_a_hist('000918')` | daily |
| `idx_value300` | 沪深300价值 | `index_zh_a_hist('000919')` | daily |
| `idx_hk_dividend` | 中证港股通高股息 | `index_zh_a_hist('930914')` | daily |
| `idx_equity_fund` | 偏股混合基金指数 | `index_zh_a_hist('885001')` | daily |
| `pe_csi300` | 沪深300市盈率(PE1) | `stock_zh_index_value_csindex('000300')` | monthly |
| `div_yield_csi300` | 沪深300股息率(%) | same | monthly |
| `cn_10y_bond` | 中国10年期国债(%) | `bond_zh_us_rate()` | daily |
| `us_10y_bond` | 美国10年期国债(%) | same | daily |
| `m2_yoy` | M2同比增速(%) | `macro_china_m2_yearly()` | monthly |
| `pmi_mfg` | 制造业PMI | `macro_china_pmi()` | monthly |
| `ah_premium` | AH溢价指数 | `stock_zh_ah_spot_em()` avg | daily |
| (already exist) | north_flow, qvix, gold, wti_oil | — | daily |

## Signal Rules

| Indicator | Signal logic |
|---|---|
| 五年之锚 deviation | >+20% → overvalued; -10%~+20% → neutral; <-10% → undervalued |
| 股债利差(内资) | >3% → very attractive; 1-3% → attractive; <1% → expensive |
| 股债利差(外资) | >2% → attractive; 0-2% → neutral; <0% → expensive |
| 三棱镜 signal count | 2-3 → confirmed trend; 1 → weak; 0 → no signal |
| 红利股息率利差 | >3% → very attractive; 1-3% → attractive; <1% → normal |
| 红利40日收益差 | >8% → overextended; <-5% → buy; else neutral |
| QVIX | <15 complacent; 15-25 normal; >25 fearful; >35 panic |
| AH premium | <120 neutral; 120-140 moderate premium; >140 high premium |

---

## Task 1: Extend macro_fetcher.py with 13 new indicators

**Files:**
- Modify: `data_analyst/fetchers/macro_fetcher.py`

**What to add:** 13 new fetch functions and register them in `FETCH_FUNCTIONS` + `MACRO_INDICATORS` dicts.

**Step 1: Add fetch functions after line 235 (after `fetch_north_flow`)**

```python
def fetch_index_daily(symbol: str, start_date: str) -> pd.DataFrame:
    """
    通用指数日线拉取 (index_zh_a_hist)
    Returns DataFrame with columns: [date, value]
    """
    if not HAS_AKSHARE:
        raise RuntimeError("AKShare 未安装")
    start_yyyymmdd = start_date.replace('-', '')
    df = ak.index_zh_a_hist(
        symbol=symbol,
        period='daily',
        start_date=start_yyyymmdd,
        end_date='99991231',
    )
    if df is None or df.empty:
        return pd.DataFrame()
    df['日期'] = pd.to_datetime(df['日期'])
    df = df[['日期', '收盘']].rename(columns={'日期': 'date', '收盘': 'value'})
    return df


def _make_index_fetcher(symbol: str):
    """Return a closure that fetches a specific index symbol."""
    def fetcher(start_date: str) -> pd.DataFrame:
        return fetch_index_daily(symbol, start_date)
    return fetcher


def fetch_csi300_valuation(start_date: str) -> pd.DataFrame:
    """
    拉取沪深300 PE + 股息率 (monthly from csindex)
    Stores two indicators: pe_csi300 and div_yield_csi300
    Returns empty (caller handles both via special path)
    """
    if not HAS_AKSHARE:
        raise RuntimeError("AKShare 未安装")
    df = ak.stock_zh_index_value_csindex(symbol='000300')
    if df is None or df.empty:
        return pd.DataFrame()
    df['日期'] = pd.to_datetime(df['日期'])
    df = df[['日期', '市盈率1', '股息率1']].rename(
        columns={'日期': 'date', '市盈率1': 'pe', '股息率1': 'div_yield'}
    )
    start_dt = pd.to_datetime(start_date)
    df = df[df['date'] >= start_dt]
    return df


def fetch_bond_yields(start_date: str) -> pd.DataFrame:
    """
    拉取中美10年期国债收益率 (daily)
    Returns empty (caller handles two indicators)
    """
    if not HAS_AKSHARE:
        raise RuntimeError("AKShare 未安装")
    df = ak.bond_zh_us_rate(start_date=start_date.replace('-', ''))
    if df is None or df.empty:
        return pd.DataFrame()
    df['日期'] = pd.to_datetime(df['日期'])
    df = df[['日期', '中国国债收益率10年', '美国国债收益率10年']].rename(
        columns={
            '日期': 'date',
            '中国国债收益率10年': 'cn_10y',
            '美国国债收益率10年': 'us_10y',
        }
    )
    start_dt = pd.to_datetime(start_date)
    df = df[df['date'] >= start_dt]
    return df


def fetch_m2_yoy(start_date: str) -> pd.DataFrame:
    """M2同比增速 (monthly)"""
    if not HAS_AKSHARE:
        raise RuntimeError("AKShare 未安装")
    df = ak.macro_china_m2_yearly()
    if df is None or df.empty:
        return pd.DataFrame()
    # columns: 月份, 今值, 预测值, 前值
    df['月份'] = pd.to_datetime(df['月份'])
    df = df[['月份', '今值']].rename(columns={'月份': 'date', '今值': 'value'})
    df['value'] = pd.to_numeric(df['value'], errors='coerce')
    start_dt = pd.to_datetime(start_date)
    df = df[df['date'] >= start_dt].dropna(subset=['value'])
    return df


def fetch_pmi_mfg(start_date: str) -> pd.DataFrame:
    """制造业PMI (monthly)"""
    if not HAS_AKSHARE:
        raise RuntimeError("AKShare 未安装")
    df = ak.macro_china_pmi()
    if df is None or df.empty:
        return pd.DataFrame()
    # columns: 月份, 制造业-指数, ...
    df['月份'] = pd.to_datetime(df['月份'])
    col = '制造业-指数' if '制造业-指数' in df.columns else df.columns[1]
    df = df[['月份', col]].rename(columns={'月份': 'date', col: 'value'})
    df['value'] = pd.to_numeric(df['value'], errors='coerce')
    start_dt = pd.to_datetime(start_date)
    df = df[df['date'] >= start_dt].dropna(subset=['value'])
    return df


def fetch_ah_premium(start_date: str) -> pd.DataFrame:
    """AH溢价指数 (daily, avg of all AH pairs)"""
    if not HAS_AKSHARE:
        raise RuntimeError("AKShare 未安装")
    df = ak.stock_zh_ah_spot_em()
    if df is None or df.empty:
        return pd.DataFrame()
    # This returns a spot snapshot, not history - use index_zh_a_hist for SAHK:
    # AH premium index = 000821 (恒生AH股溢价指数)
    start_yyyymmdd = start_date.replace('-', '')
    df2 = ak.index_zh_a_hist(
        symbol='000821',
        period='daily',
        start_date=start_yyyymmdd,
        end_date='99991231',
    )
    if df2 is None or df2.empty:
        return pd.DataFrame()
    df2['日期'] = pd.to_datetime(df2['日期'])
    df2 = df2[['日期', '收盘']].rename(columns={'日期': 'date', '收盘': 'value'})
    return df2
```

**Step 2: Update `MACRO_INDICATORS` dict (add after `north_flow` entry)**

```python
    # Index daily prices
    'idx_all_a':       {'name': '中证全A',         'source': 'index_zh_a_hist', 'params': {'symbol': '000985'}},
    'idx_csi300':      {'name': '沪深300',          'source': 'index_zh_a_hist', 'params': {'symbol': '000300'}},
    'idx_csi500':      {'name': '中证500',          'source': 'index_zh_a_hist', 'params': {'symbol': '000905'}},
    'idx_csi1000':     {'name': '中证1000',         'source': 'index_zh_a_hist', 'params': {'symbol': '000852'}},
    'idx_dividend':    {'name': '中证红利',          'source': 'index_zh_a_hist', 'params': {'symbol': '000922'}},
    'idx_growth300':   {'name': '沪深300成长',      'source': 'index_zh_a_hist', 'params': {'symbol': '000918'}},
    'idx_value300':    {'name': '沪深300价值',      'source': 'index_zh_a_hist', 'params': {'symbol': '000919'}},
    'idx_hk_dividend': {'name': '港股通高股息',     'source': 'index_zh_a_hist', 'params': {'symbol': '930914'}},
    'idx_equity_fund': {'name': '偏股混合基金指数', 'source': 'index_zh_a_hist', 'params': {'symbol': '885001'}},
    # Valuations (monthly)
    'pe_csi300':       {'name': '沪深300 PE',       'source': 'csindex_valuation', 'params': {}},
    'div_yield_csi300':{'name': '沪深300股息率',    'source': 'csindex_valuation', 'params': {}},
    # Bond yields (daily)
    'cn_10y_bond':     {'name': '中国10Y国债收益率', 'source': 'bond_yields',      'params': {}},
    'us_10y_bond':     {'name': '美国10Y国债收益率', 'source': 'bond_yields',      'params': {}},
    # Macro monthly
    'm2_yoy':          {'name': 'M2同比增速',        'source': 'macro_china_m2_yearly', 'params': {}},
    'pmi_mfg':         {'name': '制造业PMI',         'source': 'macro_china_pmi',       'params': {}},
    # AH premium
    'ah_premium':      {'name': 'AH溢价指数',        'source': 'ah_premium',            'params': {}},
```

**Step 3: Update `FETCH_FUNCTIONS` dict and add special multi-indicator handlers**

```python
# Add to FETCH_FUNCTIONS
for sym_key, sym_code in [
    ('idx_all_a','000985'), ('idx_csi300','000300'), ('idx_csi500','000905'),
    ('idx_csi1000','000852'), ('idx_dividend','000922'),
    ('idx_growth300','000918'), ('idx_value300','000919'),
    ('idx_hk_dividend','930914'), ('idx_equity_fund','885001'),
]:
    FETCH_FUNCTIONS[sym_key] = _make_index_fetcher(sym_code)

FETCH_FUNCTIONS['m2_yoy']    = fetch_m2_yoy
FETCH_FUNCTIONS['pmi_mfg']   = fetch_pmi_mfg
FETCH_FUNCTIONS['ah_premium'] = fetch_ah_premium
```

**Step 4: Add special-case handling for multi-indicator fetchers in `fetch_all_indicators`**

Add a new function `fetch_valuation_and_bonds()` that handles `pe_csi300 / div_yield_csi300` and `cn_10y_bond / us_10y_bond` in one call, since both need a single AKShare call but write two rows per date.

```python
def fetch_csi300_valuation_indicators() -> dict:
    """Fetch and save pe_csi300 + div_yield_csi300 (one AKShare call)."""
    results = {}
    try:
        latest = get_latest_date('pe_csi300')
        start_date = (pd.to_datetime(latest) + timedelta(days=1)).strftime('%Y-%m-%d') if latest else MACRO_DATA_START
        if latest and latest >= date.today().strftime('%Y-%m-%d'):
            return {'pe_csi300': {'success': True, 'count': 0, 'error': '已是最新'},
                    'div_yield_csi300': {'success': True, 'count': 0, 'error': '已是最新'}}
        df = fetch_csi300_valuation(start_date)
        if df.empty:
            return {'pe_csi300': {'success': True, 'count': 0, 'error': '无新数据'},
                    'div_yield_csi300': {'success': True, 'count': 0, 'error': '无新数据'}}
        pe_df = df[['date', 'pe']].rename(columns={'pe': 'value'})
        dy_df = df[['date', 'div_yield']].rename(columns={'div_yield': 'value'})
        n_pe = save_data('pe_csi300', pe_df)
        n_dy = save_data('div_yield_csi300', dy_df)
        results['pe_csi300'] = {'success': True, 'count': n_pe, 'error': None}
        results['div_yield_csi300'] = {'success': True, 'count': n_dy, 'error': None}
    except Exception as e:
        results['pe_csi300'] = {'success': False, 'count': 0, 'error': str(e)}
        results['div_yield_csi300'] = {'success': False, 'count': 0, 'error': str(e)}
    return results


def fetch_bond_yield_indicators() -> dict:
    """Fetch and save cn_10y_bond + us_10y_bond (one AKShare call)."""
    results = {}
    try:
        latest = get_latest_date('cn_10y_bond')
        start_date = (pd.to_datetime(latest) + timedelta(days=1)).strftime('%Y-%m-%d') if latest else MACRO_DATA_START
        if latest and latest >= date.today().strftime('%Y-%m-%d'):
            return {'cn_10y_bond': {'success': True, 'count': 0, 'error': '已是最新'},
                    'us_10y_bond': {'success': True, 'count': 0, 'error': '已是最新'}}
        df = fetch_bond_yields(start_date)
        if df.empty:
            return {'cn_10y_bond': {'success': True, 'count': 0, 'error': '无新数据'},
                    'us_10y_bond': {'success': True, 'count': 0, 'error': '无新数据'}}
        cn_df = df[['date', 'cn_10y']].rename(columns={'cn_10y': 'value'}).dropna()
        us_df = df[['date', 'us_10y']].rename(columns={'us_10y': 'value'}).dropna()
        n_cn = save_data('cn_10y_bond', cn_df)
        n_us = save_data('us_10y_bond', us_df)
        results['cn_10y_bond'] = {'success': True, 'count': n_cn, 'error': None}
        results['us_10y_bond'] = {'success': True, 'count': n_us, 'error': None}
    except Exception as e:
        results['cn_10y_bond'] = {'success': False, 'count': 0, 'error': str(e)}
        results['us_10y_bond'] = {'success': False, 'count': 0, 'error': str(e)}
    return results
```

**Step 5: Update `fetch_all_indicators` to call the special handlers**

```python
def fetch_all_indicators() -> dict:
    results = {}
    # Single-indicator fetchers (existing + new index/monthly fetchers)
    skip = {'pe_csi300', 'div_yield_csi300', 'cn_10y_bond', 'us_10y_bond'}
    for indicator in FETCH_FUNCTIONS.keys():
        if indicator in skip:
            continue
        success, count, error = fetch_indicator(indicator)
        results[indicator] = {'success': success, 'count': count, 'error': error,
                              'name': MACRO_INDICATORS.get(indicator, {}).get('name', indicator)}
    # Multi-indicator fetchers
    results.update(fetch_csi300_valuation_indicators())
    results.update(fetch_bond_yield_indicators())
    return results
```

**Step 6: Smoke-test the new fetcher**

```bash
cd /Users/zhaobo/data0/person/myTrader
DB_ENV=online python3 -c "
from data_analyst.fetchers.macro_fetcher import fetch_index_daily, fetch_bond_yields, fetch_csi300_valuation
import pandas as pd
# Test index
df = fetch_index_daily('000985', '20260101')
print('全A rows:', len(df), df.tail(2).to_string())
# Test bonds
df2 = fetch_bond_yields('20260101')
print('bonds rows:', len(df2), df2.tail(2).to_string())
# Test valuation
df3 = fetch_csi300_valuation('20250101')
print('valuation rows:', len(df3), df3.tail(2).to_string())
"
```

Expected: 3 DataFrames printed with recent data (no exceptions).

**Step 7: Run full fetch (this takes ~3 min, incremental)**

```bash
DB_ENV=online python3 -m data_analyst.fetchers.macro_fetcher
```

Expected: All new indicators show row counts > 0.

**Step 8: Commit**

```bash
git add data_analyst/fetchers/macro_fetcher.py
git commit -m "feat(macro-fetcher): add 13 new market overview indicators"
```

---

## Task 2: Create market_overview calculator module

**Files:**
- Create: `data_analyst/market_overview/__init__.py`
- Create: `data_analyst/market_overview/calculator.py`

**What it computes:** All derived signals from the raw `macro_data` values.

**Step 1: Create `__init__.py`**

```python
# data_analyst/market_overview/__init__.py
```
(empty file)

**Step 2: Create `calculator.py`**

```python
# -*- coding: utf-8 -*-
"""
大盘看板信号计算器

从 macro_data 表读取已存储的指标，计算衍生信号:
  - 五年之锚 (中证全A vs 5年均线偏离)
  - 股债性价比 (内资/外资视角)
  - 规模轮动三棱镜 (沪深300 vs 中证1000)
  - 成长/价值轮动三棱镜
  - 中证红利股息率利差
  - 中证红利 40日相对收益
  - 红利A vs 港股40日收益差
  - 偏股基金3年滚动年化收益
  - 宏观脉冲 (已有: 北向/QVIX + 新增: M2/PMI)
  - 全市场换手率 (from trade_stock_daily)
"""
import os
import sys
from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from config.db import execute_query

# ============================================================
# DB helpers
# ============================================================

def _load_series(indicator: str, days: int = 1500) -> pd.Series:
    """Load a single indicator time series from macro_data, indexed by date."""
    cutoff = (date.today() - timedelta(days=days)).strftime('%Y-%m-%d')
    rows = execute_query(
        "SELECT date, value FROM macro_data WHERE indicator = %s AND date >= %s ORDER BY date",
        (indicator, cutoff),
    )
    if not rows:
        return pd.Series(dtype=float)
    s = pd.Series(
        {r['date']: float(r['value']) for r in rows if r['value'] is not None}
    )
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _to_series_json(s: pd.Series, tail: int = 500) -> list:
    """Convert last N rows of a Series to [{date, value}] list for API response."""
    s2 = s.dropna().tail(tail)
    return [{'date': d.strftime('%Y-%m-%d'), 'value': round(float(v), 4)} for d, v in s2.items()]


def _signal(value: float, thresholds: list, labels: list) -> str:
    """
    Map a value to a signal label using threshold breakpoints.
    thresholds: ascending list of breakpoints
    labels: len(thresholds)+1 labels from lowest to highest bucket
    """
    for i, t in enumerate(thresholds):
        if value < t:
            return labels[i]
    return labels[-1]


# ============================================================
# 1. 五年之锚
# ============================================================

def calc_anchor_5y() -> dict:
    """
    中证全A vs 5年移动均线 (1250交易日)
    Signal: deviation_pct < -10 -> undervalued; > 20 -> overvalued; else neutral
    """
    s = _load_series('idx_all_a', days=1500 * 2)  # need 2500 days for 1250d MA
    if len(s) < 100:
        return {'available': False}

    ma5y = s.rolling(window=1250, min_periods=250).mean()
    deviation = (s - ma5y) / ma5y * 100

    current = float(s.iloc[-1])
    current_ma = float(ma5y.iloc[-1]) if not pd.isna(ma5y.iloc[-1]) else None
    current_dev = float(deviation.iloc[-1]) if not pd.isna(deviation.iloc[-1]) else None
    last_date = s.index[-1].strftime('%Y-%m-%d')

    sig = 'unknown'
    if current_dev is not None:
        sig = _signal(current_dev,
                      thresholds=[-10, 20],
                      labels=['undervalued', 'neutral', 'overvalued'])

    # Series: index + ma + deviation (last 500 trading days)
    combined = pd.DataFrame({'value': s, 'ma5y': ma5y, 'deviation': deviation}).dropna(subset=['value'])
    series = [
        {'date': d.strftime('%Y-%m-%d'),
         'value': round(float(r['value']), 2),
         'ma5y': round(float(r['ma5y']), 2) if not pd.isna(r['ma5y']) else None,
         'deviation': round(float(r['deviation']), 2) if not pd.isna(r['deviation']) else None}
        for d, r in combined.tail(500).iterrows()
    ]

    return {
        'available': True,
        'last_date': last_date,
        'current': round(current, 2),
        'ma5y': round(current_ma, 2) if current_ma else None,
        'deviation_pct': round(current_dev, 2) if current_dev else None,
        'signal': sig,
        'signal_text': {'undervalued': '低估', 'neutral': '合理', 'overvalued': '高估'}.get(sig, '-'),
        'series': series,
    }


# ============================================================
# 2. 股债性价比
# ============================================================

def calc_stock_bond_spread() -> dict:
    """
    股债性价比 (内资/外资双视角)
    PE倒数(%) = 100/PE(沪深300)
    内资利差 = PE倒数 - 中国10Y国债
    外资利差 = PE倒数 - 美国10Y国债
    """
    pe = _load_series('pe_csi300', days=1500).dropna()
    cn = _load_series('cn_10y_bond', days=1500).dropna()
    us = _load_series('us_10y_bond', days=1500).dropna()

    if pe.empty or cn.empty:
        return {'available': False}

    # Forward-fill monthly PE to daily alignment
    all_dates = cn.index.union(us.index)
    pe_daily = pe.reindex(all_dates).ffill()

    ep = (100.0 / pe_daily).rename('ep')  # earnings yield %

    spread_cn = (ep - cn).rename('spread_cn').dropna()
    spread_us = (ep - us).rename('spread_us').dropna()

    def _last(s):
        return round(float(s.iloc[-1]), 3) if not s.empty else None

    cur_ep = _last(ep)
    cur_cn = _last(cn)
    cur_us = _last(us)
    cur_spread_cn = _last(spread_cn)
    cur_spread_us = _last(spread_us)
    last_date = cn.index[-1].strftime('%Y-%m-%d')

    sig_cn = _signal(cur_spread_cn or 0,
                     thresholds=[1, 3],
                     labels=['expensive', 'neutral', 'attractive'])
    sig_us = _signal(cur_spread_us or 0,
                     thresholds=[0, 2],
                     labels=['expensive', 'neutral', 'attractive'])

    label_map = {'attractive': '高性价比', 'neutral': '中性', 'expensive': '偏贵'}

    # Build merged series for chart
    merged = pd.DataFrame({'ep': ep, 'cn': cn, 'us': us,
                           'spread_cn': spread_cn, 'spread_us': spread_us}).dropna(subset=['ep', 'cn'])
    series = [
        {'date': d.strftime('%Y-%m-%d'),
         'ep': round(float(r['ep']), 3),
         'cn_bond': round(float(r['cn']), 3) if not pd.isna(r['cn']) else None,
         'us_bond': round(float(r['us']), 3) if not pd.isna(r['us']) else None,
         'spread_cn': round(float(r['spread_cn']), 3) if not pd.isna(r['spread_cn']) else None,
         'spread_us': round(float(r['spread_us']), 3) if not pd.isna(r['spread_us']) else None}
        for d, r in merged.tail(500).iterrows()
    ]

    return {
        'available': True,
        'last_date': last_date,
        'pe': round(float(pe.iloc[-1]), 2) if not pe.empty else None,
        'earnings_yield_pct': cur_ep,
        'cn_bond_yield': cur_cn,
        'us_bond_yield': cur_us,
        'spread_cn': cur_spread_cn,
        'spread_us': cur_spread_us,
        'signal_cn': sig_cn,
        'signal_us': sig_us,
        'signal_cn_text': label_map.get(sig_cn, '-'),
        'signal_us_text': label_map.get(sig_us, '-'),
        'series': series,
    }


# ============================================================
# 3. 风格轮动三棱镜 (通用)
# ============================================================

def _calc_tri_prism(key_a: str, key_b: str, name_a: str, name_b: str) -> dict:
    """
    三棱镜通用计算: A vs B ratio
    Signal 1 (boll): ratio 上穿252d布林上轨 → A强; 下穿下轨 → B强
    Signal 2 (ma5y): ratio > 1250d MA → A强; < MA → B强
    Signal 3 (mom40): 40d收益差 > 252d均线 → A强动量; < → B强动量

    Returns signals dict + series
    """
    a = _load_series(key_a, days=1500 * 2)
    b = _load_series(key_b, days=1500 * 2)
    if len(a) < 300 or len(b) < 300:
        return {'available': False}

    # Align
    merged = pd.DataFrame({'a': a, 'b': b}).dropna()
    ratio = (merged['a'] / merged['b']).rename('ratio')

    # Signal 1: Bollinger (252d, 2 std)
    roll_mean = ratio.rolling(252, min_periods=100).mean()
    roll_std  = ratio.rolling(252, min_periods=100).std()
    upper = roll_mean + 2 * roll_std
    lower = roll_mean - 2 * roll_std
    boll_sig = 0
    if not pd.isna(ratio.iloc[-1]):
        if ratio.iloc[-1] > upper.iloc[-1]:
            boll_sig = 1   # A 偏强（高于上轨）
        elif ratio.iloc[-1] < lower.iloc[-1]:
            boll_sig = -1  # B 偏强（低于下轨）

    # Signal 2: 5Y MA
    ma5y = ratio.rolling(1250, min_periods=250).mean()
    ma_sig = 0
    if not pd.isna(ma5y.iloc[-1]):
        ma_sig = 1 if ratio.iloc[-1] > ma5y.iloc[-1] else -1

    # Signal 3: 40d momentum difference
    ret_a = merged['a'].pct_change(40)
    ret_b = merged['b'].pct_change(40)
    ret_diff = ret_a - ret_b
    diff_ma = ret_diff.rolling(252, min_periods=100).mean()
    mom_sig = 0
    if not pd.isna(ret_diff.iloc[-1]) and not pd.isna(diff_ma.iloc[-1]):
        mom_sig = 1 if ret_diff.iloc[-1] > diff_ma.iloc[-1] else -1

    total = boll_sig + ma_sig + mom_sig  # range -3 to +3
    # Positive → A stronger, Negative → B stronger
    if total >= 2:
        direction = name_a
        strength = 'confirmed'
    elif total <= -2:
        direction = name_b
        strength = 'confirmed'
    elif abs(total) == 1:
        direction = name_a if total > 0 else name_b
        strength = 'weak'
    else:
        direction = 'neutral'
        strength = 'neutral'

    # Series: ratio + bollinger bands (last 500)
    series_df = pd.DataFrame({
        'ratio': ratio,
        'upper': upper,
        'lower': lower,
        'ma5y': ma5y,
    }).dropna(subset=['ratio'])
    series = [
        {'date': d.strftime('%Y-%m-%d'),
         'ratio': round(float(r['ratio']), 4),
         'upper': round(float(r['upper']), 4) if not pd.isna(r['upper']) else None,
         'lower': round(float(r['lower']), 4) if not pd.isna(r['lower']) else None,
         'ma5y': round(float(r['ma5y']), 4) if not pd.isna(r['ma5y']) else None}
        for d, r in series_df.tail(500).iterrows()
    ]

    return {
        'available': True,
        'last_date': merged.index[-1].strftime('%Y-%m-%d'),
        'signals': {
            'boll': boll_sig,
            'ma5y': ma_sig,
            'momentum40d': mom_sig,
        },
        'total': total,
        'direction': direction,
        'strength': strength,
        'name_a': name_a,
        'name_b': name_b,
        'series': series,
    }


def calc_scale_rotation() -> dict:
    """沪深300 vs 中证1000 规模轮动"""
    return _calc_tri_prism('idx_csi300', 'idx_csi1000', '大盘', '小盘')


def calc_style_rotation() -> dict:
    """沪深300成长 vs 沪深300价值 成长/价值轮动"""
    return _calc_tri_prism('idx_growth300', 'idx_value300', '成长', '价值')


# ============================================================
# 4. 中证红利追踪
# ============================================================

def calc_dividend_tracking() -> dict:
    """
    红利股息率利差 + 40日相对收益 + 港股红利对比
    """
    dy = _load_series('div_yield_csi300', days=1500)   # CSI300 dividend yield %
    cn = _load_series('cn_10y_bond', days=1500)
    div_idx   = _load_series('idx_dividend', days=300)
    all_a_idx = _load_series('idx_all_a', days=300)
    hk_div    = _load_series('idx_hk_dividend', days=300)

    result = {'available': True}

    # --- a) 股息率利差 ---
    if not dy.empty and not cn.empty:
        all_dates = cn.index
        dy_daily = dy.reindex(all_dates).ffill()
        spread = (dy_daily - cn).dropna()
        cur_dy = round(float(dy.iloc[-1]), 3) if not dy.empty else None
        cur_cn = round(float(cn.iloc[-1]), 3) if not cn.empty else None
        cur_spread = round(float(spread.iloc[-1]), 3) if not spread.empty else None
        sig = _signal(cur_spread or 0,
                      thresholds=[1, 3],
                      labels=['normal', 'attractive', 'very_attractive'])
        label_map = {'normal': '一般', 'attractive': '有吸引力', 'very_attractive': '非常有吸引力'}
        dy_series = pd.DataFrame({'dy': dy_daily, 'cn': cn, 'spread': spread}).dropna(subset=['dy'])
        result['yield_spread'] = {
            'div_yield': cur_dy,
            'cn_bond': cur_cn,
            'spread': cur_spread,
            'signal': sig,
            'signal_text': label_map.get(sig, '-'),
            'series': [
                {'date': d.strftime('%Y-%m-%d'),
                 'div_yield': round(float(r['dy']), 3),
                 'cn_bond': round(float(r['cn']), 3) if not pd.isna(r['cn']) else None,
                 'spread': round(float(r['spread']), 3) if not pd.isna(r['spread']) else None}
                for d, r in dy_series.tail(300).iterrows()
            ]
        }
    else:
        result['yield_spread'] = {'available': False}

    # --- b) 红利40日相对收益 (vs 全A) ---
    if not div_idx.empty and not all_a_idx.empty:
        merged = pd.DataFrame({'div': div_idx, 'all': all_a_idx}).dropna()
        ret40_div = merged['div'].pct_change(40) * 100
        ret40_all = merged['all'].pct_change(40) * 100
        diff = (ret40_div - ret40_all).dropna()
        cur_diff = round(float(diff.iloc[-1]), 2) if not diff.empty else None
        sig2 = _signal(cur_diff or 0,
                       thresholds=[-5, 8],
                       labels=['buy_opportunity', 'neutral', 'overextended'])
        label_map2 = {'buy_opportunity': '回调机会', 'neutral': '中性', 'overextended': '过热'}
        result['rel_return_40d'] = {
            'value': cur_diff,
            'signal': sig2,
            'signal_text': label_map2.get(sig2, '-'),
            'series': _to_series_json(diff, tail=300),
        }
    else:
        result['rel_return_40d'] = {'available': False}

    # --- c) 红利A vs 港股 40日收益差 ---
    if not div_idx.empty and not hk_div.empty:
        merged2 = pd.DataFrame({'a': div_idx, 'hk': hk_div}).dropna()
        ret40_a  = merged2['a'].pct_change(40) * 100
        ret40_hk = merged2['hk'].pct_change(40) * 100
        diff2 = (ret40_a - ret40_hk).dropna()
        cur_diff2 = round(float(diff2.iloc[-1]), 2) if not diff2.empty else None
        sig3 = _signal(cur_diff2 or 0,
                       thresholds=[-5, 5],
                       labels=['hk_preferred', 'neutral', 'a_preferred'])
        label_map3 = {'hk_preferred': '港股红利占优', 'neutral': '持平', 'a_preferred': 'A股红利占优'}
        result['ah_rel_return_40d'] = {
            'value': cur_diff2,
            'signal': sig3,
            'signal_text': label_map3.get(sig3, '-'),
            'series': _to_series_json(diff2, tail=300),
        }
    else:
        result['ah_rel_return_40d'] = {'available': False}

    return result


# ============================================================
# 5. 偏股基金3年滚动年化收益
# ============================================================

def calc_equity_fund_rolling() -> dict:
    """
    偏股混合型基金指数 885001 的3年(756交易日)滚动年化收益
    > 30% → 泡沫警示; < -10% → 底部区域
    """
    s = _load_series('idx_equity_fund', days=1500 * 2)
    if len(s) < 756:
        return {'available': False}

    roll3y = s.pct_change(756) * 100  # 3-year total return %
    # Annualized: (1 + r/100)^(1/3) - 1
    ann = ((1 + roll3y / 100) ** (1.0 / 3) - 1) * 100

    cur = round(float(ann.iloc[-1]), 2) if not pd.isna(ann.iloc[-1]) else None
    last_date = s.index[-1].strftime('%Y-%m-%d')
    sig = _signal(cur or 0,
                  thresholds=[-10, 30],
                  labels=['bottom', 'normal', 'bubble'])
    label_map = {'bottom': '底部区域', 'normal': '正常', 'bubble': '泡沫警示'}

    return {
        'available': True,
        'last_date': last_date,
        'current_pct': cur,
        'signal': sig,
        'signal_text': label_map.get(sig, '-'),
        'series': _to_series_json(ann.dropna(), tail=500),
    }


# ============================================================
# 6. 宏观脉冲 (point-in-time stats)
# ============================================================

def calc_macro_pulse() -> dict:
    """
    North flow, QVIX, M2, PMI, AH premium — latest value + signal
    """
    def _latest(ind: str, days: int = 30) -> Optional[float]:
        s = _load_series(ind, days=days)
        return round(float(s.iloc[-1]), 3) if not s.empty else None

    qvix = _latest('qvix')
    north_5d_rows = execute_query(
        "SELECT date, value FROM macro_data WHERE indicator='north_flow' ORDER BY date DESC LIMIT 5"
    )
    north_today = float(north_5d_rows[0]['value']) if north_5d_rows else None
    north_5d = sum(float(r['value']) for r in north_5d_rows) if north_5d_rows else None
    m2 = _latest('m2_yoy', days=45)
    pmi = _latest('pmi_mfg', days=45)
    ah = _latest('ah_premium', days=10)

    # QVIX signal
    qvix_sig = _signal(qvix or 20, [15, 25, 35], ['complacent', 'normal', 'fearful', 'panic'])
    qvix_label = {'complacent': '低波动', 'normal': '正常', 'fearful': '恐慌', 'panic': '极度恐慌'}

    return {
        'qvix': {'value': qvix, 'signal': qvix_sig, 'signal_text': qvix_label.get(qvix_sig, '-')},
        'north_flow': {
            'today': north_today,
            'sum_5d': round(north_5d, 2) if north_5d else None,
            'signal': 'inflow' if (north_5d or 0) > 0 else 'outflow',
        },
        'm2_yoy': {'value': m2},
        'pmi_mfg': {
            'value': pmi,
            'signal': 'expansion' if (pmi or 0) >= 50 else 'contraction',
            'signal_text': '扩张' if (pmi or 0) >= 50 else '收缩',
        },
        'ah_premium': {
            'value': ah,
            'signal': _signal(ah or 130, [120, 140], ['low', 'moderate', 'high']),
            'signal_text': {0: '低溢价', 1: '中等溢价', 2: '高溢价'}.get(
                0 if (ah or 130) < 120 else (1 if (ah or 130) < 140 else 2), '-'
            ),
        },
    }


# ============================================================
# 7. 全市场换手率 (from trade_stock_daily)
# ============================================================

def calc_market_turnover() -> dict:
    """
    全A平均换手率: AVG(turnover_rate) from trade_stock_daily, last 5 trading days
    Historical percentile using 252d rolling window
    """
    rows = execute_query("""
        SELECT trade_date, AVG(turnover_rate) AS avg_tr
        FROM trade_stock_daily
        WHERE trade_date >= DATE_SUB(CURDATE(), INTERVAL 400 DAY)
          AND turnover_rate > 0
        GROUP BY trade_date
        ORDER BY trade_date
    """)
    if not rows:
        return {'available': False}

    s = pd.Series({r['trade_date']: float(r['avg_tr']) for r in rows})
    s.index = pd.to_datetime(s.index)
    s = s.sort_index()

    cur = round(float(s.iloc[-1]), 3) if not s.empty else None
    # Percentile rank over last 252 trading days
    window = s.tail(252)
    pct_rank = round(float((window < cur).mean() * 100), 1) if cur and len(window) > 10 else None

    sig = _signal(cur or 1.5, [0.8, 3.0], ['low', 'normal', 'high'])
    label = {'low': '冷清', 'normal': '正常', 'high': '活跃'}

    return {
        'available': True,
        'last_date': s.index[-1].strftime('%Y-%m-%d'),
        'value': cur,
        'pct_rank': pct_rank,
        'signal': sig,
        'signal_text': label.get(sig, '-'),
        'series': _to_series_json(s, tail=252),
    }


# ============================================================
# Master compute
# ============================================================

def compute_all() -> dict:
    """Compute all market overview indicators. Called by API (cached 6h)."""
    return {
        'updated_at': date.today().strftime('%Y-%m-%d'),
        'anchor_5y':          calc_anchor_5y(),
        'stock_bond_spread':  calc_stock_bond_spread(),
        'scale_rotation':     calc_scale_rotation(),
        'style_rotation':     calc_style_rotation(),
        'dividend':           calc_dividend_tracking(),
        'equity_fund_rolling': calc_equity_fund_rolling(),
        'macro_pulse':        calc_macro_pulse(),
        'market_turnover':    calc_market_turnover(),
    }
```

**Step 3: Smoke-test the calculator**

```bash
DB_ENV=online python3 -c "
from data_analyst.market_overview.calculator import compute_all
import json
result = compute_all()
for k, v in result.items():
    if isinstance(v, dict):
        avail = v.get('available', True)
        print(f'{k}: available={avail}, keys={list(v.keys())[:5]}')
    else:
        print(f'{k}: {v}')
"
```

Expected: All 8 sections printed, most `available: True` (some monthly data may be sparse).

**Step 4: Commit**

```bash
git add data_analyst/market_overview/
git commit -m "feat(market-overview): add signal calculator for all 8 indicator groups"
```

---

## Task 3: Update YAML scheduler

**Files:**
- Modify: `tasks/02_macro.yaml`

**Step 1: Add two new tasks at the end**

```yaml
  - id: fetch_market_indices
    name: "Fetch market index prices and macro valuations"
    module: data_analyst.fetchers.macro_fetcher
    func: fetch_all_indicators
    tags: [macro, market_overview, daily]
    schedule: "17:30"
    depends_on: []
    params: {}

  - id: calc_market_overview
    name: "Compute market overview signals and cache"
    module: data_analyst.market_overview.calculator
    func: compute_all
    tags: [market_overview, daily]
    schedule: "after_gate"
    depends_on:
      - fetch_market_indices
    params: {}
```

Note: `fetch_market_indices` reuses the same `fetch_all_indicators` function — new indicators are picked up automatically since they are now registered in `FETCH_FUNCTIONS`.

**Step 2: Verify YAML loads cleanly**

```bash
python3 -m scheduler list --tag market_overview
```

Expected: Two tasks listed.

**Step 3: Commit**

```bash
git add tasks/02_macro.yaml
git commit -m "feat(scheduler): add market_overview fetch and calc tasks to daily pipeline"
```

---

## Task 4: Create API router

**Files:**
- Create: `api/routers/market_overview.py`
- Create: `api/schemas/market_overview.py`

**Step 1: Create `api/schemas/market_overview.py`**

```python
# -*- coding: utf-8 -*-
from typing import Any, Dict, Optional
from pydantic import BaseModel


class MarketOverviewResponse(BaseModel):
    updated_at: str
    anchor_5y: Dict[str, Any]
    stock_bond_spread: Dict[str, Any]
    scale_rotation: Dict[str, Any]
    style_rotation: Dict[str, Any]
    dividend: Dict[str, Any]
    equity_fund_rolling: Dict[str, Any]
    macro_pulse: Dict[str, Any]
    market_turnover: Dict[str, Any]
```

**Step 2: Create `api/routers/market_overview.py`**

```python
# -*- coding: utf-8 -*-
"""
GET /api/market-overview/summary
Returns all market overview indicators (cached 6h in Redis).
No auth required — read-only public data.
"""
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from api.dependencies import get_redis
from api.schemas.market_overview import MarketOverviewResponse

logger = logging.getLogger('myTrader.api')

router = APIRouter(prefix='/api/market-overview', tags=['market-overview'])

CACHE_KEY = 'market_overview:summary'
CACHE_TTL = 6 * 3600  # 6 hours


@router.get('/summary', response_model=MarketOverviewResponse)
async def get_market_overview_summary():
    """
    Returns full market overview dashboard data.
    Cached 6 hours in Redis. Falls back to live computation on cache miss.
    """
    redis = await get_redis()

    # Try cache first
    if redis:
        try:
            cached = await redis.get(CACHE_KEY)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning('Redis cache read failed: %s', e)

    # Compute live (runs ~5s with DB queries)
    try:
        from data_analyst.market_overview.calculator import compute_all
        data = compute_all()
    except Exception as e:
        logger.error('market_overview compute_all failed: %s', e)
        raise HTTPException(status_code=503, detail=f'Computation failed: {e}')

    # Cache result
    if redis:
        try:
            await redis.setex(CACHE_KEY, CACHE_TTL, json.dumps(data, default=str))
        except Exception as e:
            logger.warning('Redis cache write failed: %s', e)

    return data


@router.post('/refresh')
async def refresh_market_overview():
    """Force-invalidate the Redis cache and recompute."""
    redis = await get_redis()
    if redis:
        try:
            await redis.delete(CACHE_KEY)
        except Exception:
            pass
    # Trigger recompute
    return await get_market_overview_summary()
```

**Step 3: Register router in `api/main.py`**

Add to imports section (around line 19):
```python
from api.routers.market_overview import router as market_overview_router
```

Add to router registration section (after line 113):
```python
app.include_router(market_overview_router)
```

**Step 4: Test the endpoint**

```bash
curl http://localhost:8001/api/market-overview/summary | python3 -m json.tool | head -50
```

Expected: JSON with 8 top-level keys, most having `available: true`.

**Step 5: Commit**

```bash
git add api/routers/market_overview.py api/schemas/market_overview.py api/main.py
git commit -m "feat(api): add /api/market-overview/summary endpoint with Redis cache"
```

---

## Task 5: Update frontend API client

**Files:**
- Modify: `web/src/lib/api-client.ts`

**Step 1: Add types and API methods (append to end of file)**

```typescript
// ---- Market Overview Types ----

export interface TimeSeriesPoint {
  date: string;
  value: number;
}

export interface AnchorSeries {
  date: string;
  value: number;
  ma5y: number | null;
  deviation: number | null;
}

export interface Anchor5Y {
  available: boolean;
  last_date?: string;
  current?: number;
  ma5y?: number;
  deviation_pct?: number;
  signal?: 'undervalued' | 'neutral' | 'overvalued';
  signal_text?: string;
  series?: AnchorSeries[];
}

export interface StockBondSeries {
  date: string;
  ep: number;
  cn_bond: number | null;
  us_bond: number | null;
  spread_cn: number | null;
  spread_us: number | null;
}

export interface StockBondSpread {
  available: boolean;
  last_date?: string;
  pe?: number;
  earnings_yield_pct?: number;
  cn_bond_yield?: number;
  us_bond_yield?: number;
  spread_cn?: number;
  spread_us?: number;
  signal_cn?: string;
  signal_us?: string;
  signal_cn_text?: string;
  signal_us_text?: string;
  series?: StockBondSeries[];
}

export interface TriPrismSignals {
  boll: number;
  ma5y: number;
  momentum40d: number;
}

export interface RotationSeries {
  date: string;
  ratio: number;
  upper: number | null;
  lower: number | null;
  ma5y: number | null;
}

export interface TriPrismResult {
  available: boolean;
  last_date?: string;
  signals?: TriPrismSignals;
  total?: number;
  direction?: string;
  strength?: string;
  name_a?: string;
  name_b?: string;
  series?: RotationSeries[];
}

export interface DividendYieldSeries {
  date: string;
  div_yield: number;
  cn_bond: number | null;
  spread: number | null;
}

export interface DividendTracking {
  available: boolean;
  yield_spread?: {
    div_yield: number;
    cn_bond: number;
    spread: number;
    signal: string;
    signal_text: string;
    series: DividendYieldSeries[];
  };
  rel_return_40d?: {
    value: number;
    signal: string;
    signal_text: string;
    series: TimeSeriesPoint[];
  };
  ah_rel_return_40d?: {
    value: number;
    signal: string;
    signal_text: string;
    series: TimeSeriesPoint[];
  };
}

export interface EquityFundRolling {
  available: boolean;
  last_date?: string;
  current_pct?: number;
  signal?: string;
  signal_text?: string;
  series?: TimeSeriesPoint[];
}

export interface MacroPulse {
  qvix: { value: number | null; signal: string; signal_text: string };
  north_flow: { today: number | null; sum_5d: number | null; signal: string };
  m2_yoy: { value: number | null };
  pmi_mfg: { value: number | null; signal: string; signal_text: string };
  ah_premium: { value: number | null; signal: string; signal_text: string };
}

export interface MarketTurnover {
  available: boolean;
  last_date?: string;
  value?: number;
  pct_rank?: number;
  signal?: string;
  signal_text?: string;
  series?: TimeSeriesPoint[];
}

export interface MarketOverview {
  updated_at: string;
  anchor_5y: Anchor5Y;
  stock_bond_spread: StockBondSpread;
  scale_rotation: TriPrismResult;
  style_rotation: TriPrismResult;
  dividend: DividendTracking;
  equity_fund_rolling: EquityFundRolling;
  macro_pulse: MacroPulse;
  market_turnover: MarketTurnover;
}

export const marketOverviewApi = {
  summary: () => apiClient.get<MarketOverview>('/api/market-overview/summary'),
  refresh: () => apiClient.post<MarketOverview>('/api/market-overview/refresh'),
};
```

**Step 2: TypeScript check**

```bash
cd /Users/zhaobo/data0/person/myTrader/web && npx tsc --noEmit 2>&1 | head -20
```

Expected: No errors.

**Step 3: Commit**

```bash
git add web/src/lib/api-client.ts
git commit -m "feat(frontend): add MarketOverview types and marketOverviewApi client"
```

---

## Task 6: Build the Market Overview page

**Files:**
- Create: `web/src/components/market/LineChart.tsx`  (lightweight-charts wrapper)
- Create: `web/src/components/market/SignalBadge.tsx`
- Modify: `web/src/app/market/page.tsx`

### Sub-task 6a: LineChart component

**Step 1: Create `web/src/components/market/LineChart.tsx`**

```tsx
'use client';
import { useEffect, useRef } from 'react';
import { createChart, ColorType, LineStyle } from 'lightweight-charts';

interface LineSeries {
  data: { time: string; value: number }[];
  color: string;
  lineWidth?: number;
  title?: string;
}

interface LineChartProps {
  series: LineSeries[];
  height?: number;
  /** Optional horizontal reference line (e.g. 0 or 50 for PMI) */
  refLine?: number;
}

export default function LineChart({ series, height = 180, refLine }: LineChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || series.length === 0) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#6b7280',
        fontSize: 11,
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { color: '#f3f4f6' },
      },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false, fixLeftEdge: true, fixRightEdge: true },
      crosshair: { horzLine: { visible: false } },
    });

    const chartSeries = series.map((s) => {
      const ls = chart.addLineSeries({
        color: s.color,
        lineWidth: s.lineWidth ?? 1,
        title: s.title ?? '',
        priceLineVisible: false,
        lastValueVisible: false,
      });
      const validData = s.data
        .filter((d) => d.value != null && !isNaN(d.value))
        .map((d) => ({ time: d.time as import('lightweight-charts').Time, value: d.value }));
      ls.setData(validData);
      return ls;
    });

    if (refLine !== undefined) {
      chartSeries[0]?.createPriceLine({
        price: refLine,
        color: '#9ca3af',
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: String(refLine),
      });
    }

    chart.timeScale().fitContent();

    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
    };
  }, [series, height, refLine]);

  return <div ref={containerRef} className="w-full" />;
}
```

### Sub-task 6b: SignalBadge component

**Step 2: Create `web/src/components/market/SignalBadge.tsx`**

```tsx
interface SignalBadgeProps {
  signal: string;
  text: string;
  size?: 'sm' | 'md';
}

const COLOR_MAP: Record<string, string> = {
  // Positive / safe
  undervalued: 'bg-green-100 text-green-800',
  attractive: 'bg-green-100 text-green-800',
  very_attractive: 'bg-emerald-100 text-emerald-800',
  inflow: 'bg-green-100 text-green-800',
  expansion: 'bg-green-100 text-green-800',
  buy_opportunity: 'bg-green-100 text-green-800',
  bottom: 'bg-green-100 text-green-800',
  low: 'bg-green-100 text-green-800',
  // Neutral
  neutral: 'bg-gray-100 text-gray-700',
  normal: 'bg-gray-100 text-gray-700',
  complacent: 'bg-blue-50 text-blue-700',
  moderate: 'bg-yellow-50 text-yellow-700',
  // Warning
  overvalued: 'bg-amber-100 text-amber-800',
  overextended: 'bg-amber-100 text-amber-800',
  expensive: 'bg-amber-100 text-amber-800',
  fearful: 'bg-amber-100 text-amber-800',
  outflow: 'bg-amber-100 text-amber-800',
  // Danger
  bubble: 'bg-red-100 text-red-800',
  panic: 'bg-red-100 text-red-800',
  high: 'bg-red-100 text-red-800',
  contraction: 'bg-red-100 text-red-800',
};

export default function SignalBadge({ signal, text, size = 'sm' }: SignalBadgeProps) {
  const cls = COLOR_MAP[signal] ?? 'bg-gray-100 text-gray-700';
  const sizeCls = size === 'sm' ? 'text-xs px-2 py-0.5' : 'text-sm px-2.5 py-1';
  return (
    <span className={`inline-flex items-center rounded-full font-medium ${cls} ${sizeCls}`}>
      {text}
    </span>
  );
}
```

### Sub-task 6c: Market page

**Step 3: Rewrite `web/src/app/market/page.tsx`**

```tsx
'use client';
import { useQuery } from '@tanstack/react-query';
import { marketOverviewApi, MarketOverview } from '@/lib/api-client';
import LineChart from '@/components/market/LineChart';
import SignalBadge from '@/components/market/SignalBadge';

// ---- helpers ----
function num(v: number | null | undefined, decimals = 2) {
  if (v == null) return '-';
  return v.toFixed(decimals);
}

function signalArrow(total: number | undefined) {
  if (total == null) return '';
  if (total >= 2) return '[UP]';
  if (total <= -2) return '[DOWN]';
  return '[~]';
}

// ---- Section wrapper ----
function Section({ title, desc, children }: {
  title: string; desc: string; children: React.ReactNode
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="mb-3">
        <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
        <p className="text-xs text-gray-400 mt-0.5">{desc}</p>
      </div>
      {children}
    </div>
  );
}

// ---- Stat row ----
function StatRow({ label, value, unit = '', signal, signalText }: {
  label: string; value: string; unit?: string;
  signal?: string; signalText?: string;
}) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-gray-50 last:border-0">
      <span className="text-xs text-gray-500">{label}</span>
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-gray-900">{value}{unit && <span className="text-xs text-gray-400 ml-0.5">{unit}</span>}</span>
        {signal && signalText && <SignalBadge signal={signal} text={signalText} />}
      </div>
    </div>
  );
}

// ============================================================
// Main page
// ============================================================
export default function MarketPage() {
  const { data, isLoading, error, refetch } = useQuery<MarketOverview>({
    queryKey: ['market-overview'],
    queryFn: () => marketOverviewApi.summary().then((r) => r.data),
    staleTime: 30 * 60 * 1000, // 30 min
  });

  if (isLoading) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-12 text-center text-gray-400 text-sm">
        加载大盘看板...
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-12 text-center">
        <p className="text-red-500 text-sm">加载失败</p>
        <button onClick={() => refetch()} className="mt-2 text-blue-600 text-sm underline">重试</button>
      </div>
    );
  }

  const { anchor_5y: anc, stock_bond_spread: sbs, scale_rotation: scale,
          style_rotation: style, dividend: div, equity_fund_rolling: efr,
          macro_pulse: mp, market_turnover: mt } = data;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">大盘看板</h1>
          <p className="text-xs text-gray-400 mt-0.5">数据更新: {data.updated_at}</p>
        </div>
        <button
          onClick={() => refetch()}
          className="text-xs text-gray-500 hover:text-gray-700 border border-gray-200 rounded-md px-3 py-1.5"
        >
          刷新
        </button>
      </div>

      {/* ===== Row 1: 宏观脉冲 (4 stat cards) ===== */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {/* QVIX */}
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <p className="text-xs text-gray-400">QVIX 波动率</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{num(mp.qvix.value, 1)}</p>
          <div className="mt-2"><SignalBadge signal={mp.qvix.signal} text={mp.qvix.signal_text} /></div>
          <p className="text-xs text-gray-300 mt-1.5">50ETF期权隐含波动率</p>
        </div>
        {/* North Flow */}
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <p className="text-xs text-gray-400">北向资金 (近5日)</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">
            {mp.north_flow.sum_5d != null ? (mp.north_flow.sum_5d > 0 ? '+' : '') + num(mp.north_flow.sum_5d, 1) : '-'}
            <span className="text-sm text-gray-400 ml-1">亿</span>
          </p>
          <div className="mt-2">
            <SignalBadge signal={mp.north_flow.signal} text={mp.north_flow.signal === 'inflow' ? '净流入' : '净流出'} />
          </div>
          <p className="text-xs text-gray-300 mt-1.5">今日: {num(mp.north_flow.today, 1)} 亿</p>
        </div>
        {/* PMI */}
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <p className="text-xs text-gray-400">制造业 PMI</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{num(mp.pmi_mfg.value, 1)}</p>
          <div className="mt-2"><SignalBadge signal={mp.pmi_mfg.signal} text={mp.pmi_mfg.signal_text} /></div>
          <p className="text-xs text-gray-300 mt-1.5">50 以上为扩张</p>
        </div>
        {/* AH Premium */}
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <p className="text-xs text-gray-400">AH 溢价指数</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{num(mp.ah_premium.value, 1)}</p>
          <div className="mt-2"><SignalBadge signal={mp.ah_premium.signal} text={mp.ah_premium.signal_text} /></div>
          <p className="text-xs text-gray-300 mt-1.5">高于140 港股更有吸引力</p>
        </div>
      </div>

      {/* ===== Row 2: 五年之锚 + 股债性价比 ===== */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* 五年之锚 */}
        <Section
          title="五年之锚"
          desc="中证全A vs 5年移动均线 — A股有波幅少升幅，以5年均线为中枢做均值回归"
        >
          {anc.available ? (
            <>
              <div className="flex items-center gap-3 mb-3">
                <div>
                  <span className="text-2xl font-bold text-gray-900">{num(anc.current, 0)}</span>
                  <span className="text-xs text-gray-400 ml-1">点</span>
                </div>
                <div className="text-xs text-gray-500">
                  5Y均线 <span className="font-medium text-gray-700">{num(anc.ma5y, 0)}</span>
                </div>
                <div className="text-xs text-gray-500">
                  偏离 <span className={`font-medium ${(anc.deviation_pct ?? 0) > 0 ? 'text-red-600' : 'text-green-600'}`}>
                    {(anc.deviation_pct ?? 0) > 0 ? '+' : ''}{num(anc.deviation_pct, 1)}%
                  </span>
                </div>
                <SignalBadge signal={anc.signal ?? 'neutral'} text={anc.signal_text ?? '-'} />
              </div>
              <LineChart
                series={[
                  { data: (anc.series ?? []).map((d) => ({ time: d.date, value: d.value })), color: '#3b82f6', lineWidth: 1, title: '中证全A' },
                  { data: (anc.series ?? []).filter((d) => d.ma5y != null).map((d) => ({ time: d.date, value: d.ma5y! })), color: '#f59e0b', lineWidth: 1, title: '5Y均线' },
                ]}
                height={160}
              />
              <p className="text-xs text-gray-300 mt-2">
                信号规则: 偏离 &lt; -10% 低估 / -10%~+20% 合理 / &gt; +20% 高估
              </p>
            </>
          ) : (
            <p className="text-sm text-gray-400">数据不足，请先运行数据抓取任务</p>
          )}
        </Section>

        {/* 股债性价比 */}
        <Section
          title="股债性价比"
          desc="沪深300盈利收益率 vs 国债 — 利差越高A股越有吸引力"
        >
          {sbs.available ? (
            <>
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="bg-gray-50 rounded-lg p-3">
                  <p className="text-xs text-gray-400">内资视角 (vs 中国10Y)</p>
                  <p className="text-xl font-bold text-gray-900">{num(sbs.spread_cn, 2)}%</p>
                  <div className="mt-1"><SignalBadge signal={sbs.signal_cn ?? 'neutral'} text={sbs.signal_cn_text ?? '-'} /></div>
                </div>
                <div className="bg-gray-50 rounded-lg p-3">
                  <p className="text-xs text-gray-400">外资视角 (vs 美国10Y)</p>
                  <p className="text-xl font-bold text-gray-900">{num(sbs.spread_us, 2)}%</p>
                  <div className="mt-1"><SignalBadge signal={sbs.signal_us ?? 'neutral'} text={sbs.signal_us_text ?? '-'} /></div>
                </div>
              </div>
              <div className="text-xs text-gray-400 mb-2 flex gap-4">
                <span>PE: <strong className="text-gray-700">{num(sbs.pe, 1)}x</strong></span>
                <span>盈利收益率: <strong className="text-gray-700">{num(sbs.earnings_yield_pct, 2)}%</strong></span>
                <span>中国10Y: <strong className="text-gray-700">{num(sbs.cn_bond_yield, 2)}%</strong></span>
                <span>美国10Y: <strong className="text-gray-700">{num(sbs.us_bond_yield, 2)}%</strong></span>
              </div>
              <LineChart
                series={[
                  { data: (sbs.series ?? []).filter((d) => d.spread_cn != null).map((d) => ({ time: d.date, value: d.spread_cn! })), color: '#10b981', lineWidth: 1, title: '内资利差' },
                  { data: (sbs.series ?? []).filter((d) => d.spread_us != null).map((d) => ({ time: d.date, value: d.spread_us! })), color: '#6366f1', lineWidth: 1, title: '外资利差' },
                ]}
                height={140}
                refLine={0}
              />
            </>
          ) : (
            <p className="text-sm text-gray-400">数据不足</p>
          )}
        </Section>
      </div>

      {/* ===== Row 3: 风格轮动三棱镜 ===== */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* 规模轮动 */}
        <Section
          title="规模轮动三棱镜 (大盘 vs 小盘)"
          desc="沪深300 / 中证1000 比值 + 布林 + 5年均线 + 40日动量三信号"
        >
          {scale.available ? (
            <>
              <div className="flex items-center gap-3 mb-3">
                <span className="text-2xl">{signalArrow(scale.total)}</span>
                <div>
                  <p className="text-sm font-semibold text-gray-900">{scale.direction} 占优</p>
                  <p className="text-xs text-gray-400">{scale.strength === 'confirmed' ? '趋势确认' : scale.strength === 'weak' ? '信号偏弱' : '中性'}</p>
                </div>
                <div className="ml-auto flex gap-1.5 text-xs">
                  {(['boll', 'ma5y', 'momentum40d'] as const).map((k) => {
                    const v = scale.signals?.[k] ?? 0;
                    return (
                      <span key={k} className={`px-1.5 py-0.5 rounded ${v > 0 ? 'bg-blue-50 text-blue-700' : v < 0 ? 'bg-orange-50 text-orange-700' : 'bg-gray-50 text-gray-400'}`}>
                        {k === 'boll' ? 'BOLL' : k === 'ma5y' ? '5Y均' : '动量'} {v > 0 ? '+1' : v < 0 ? '-1' : '0'}
                      </span>
                    );
                  })}
                </div>
              </div>
              <LineChart
                series={[
                  { data: (scale.series ?? []).map((d) => ({ time: d.date, value: d.ratio })), color: '#3b82f6', lineWidth: 1, title: '300/1000' },
                  { data: (scale.series ?? []).filter((d) => d.upper != null).map((d) => ({ time: d.date, value: d.upper! })), color: '#d1d5db', lineWidth: 1 },
                  { data: (scale.series ?? []).filter((d) => d.lower != null).map((d) => ({ time: d.date, value: d.lower! })), color: '#d1d5db', lineWidth: 1 },
                  { data: (scale.series ?? []).filter((d) => d.ma5y != null).map((d) => ({ time: d.date, value: d.ma5y! })), color: '#f59e0b', lineWidth: 1, title: '5Y均' },
                ]}
                height={150}
              />
              <p className="text-xs text-gray-300 mt-1.5">比值上升=大盘占优 | 灰色带=252日布林通道 | 橙线=5年均线</p>
            </>
          ) : (
            <p className="text-sm text-gray-400">数据不足</p>
          )}
        </Section>

        {/* 成长/价值轮动 */}
        <Section
          title="成长/价值轮动三棱镜"
          desc="沪深300成长 / 沪深300价值 比值 + 三信号 — 趋势性强，两三年一波"
        >
          {style.available ? (
            <>
              <div className="flex items-center gap-3 mb-3">
                <span className="text-2xl">{signalArrow(style.total)}</span>
                <div>
                  <p className="text-sm font-semibold text-gray-900">{style.direction} 占优</p>
                  <p className="text-xs text-gray-400">{style.strength === 'confirmed' ? '趋势确认' : style.strength === 'weak' ? '信号偏弱' : '中性'}</p>
                </div>
                <div className="ml-auto flex gap-1.5 text-xs">
                  {(['boll', 'ma5y', 'momentum40d'] as const).map((k) => {
                    const v = style.signals?.[k] ?? 0;
                    return (
                      <span key={k} className={`px-1.5 py-0.5 rounded ${v > 0 ? 'bg-blue-50 text-blue-700' : v < 0 ? 'bg-orange-50 text-orange-700' : 'bg-gray-50 text-gray-400'}`}>
                        {k === 'boll' ? 'BOLL' : k === 'ma5y' ? '5Y均' : '动量'} {v > 0 ? '+1' : v < 0 ? '-1' : '0'}
                      </span>
                    );
                  })}
                </div>
              </div>
              <LineChart
                series={[
                  { data: (style.series ?? []).map((d) => ({ time: d.date, value: d.ratio })), color: '#8b5cf6', lineWidth: 1, title: '成长/价值' },
                  { data: (style.series ?? []).filter((d) => d.upper != null).map((d) => ({ time: d.date, value: d.upper! })), color: '#d1d5db', lineWidth: 1 },
                  { data: (style.series ?? []).filter((d) => d.lower != null).map((d) => ({ time: d.date, value: d.lower! })), color: '#d1d5db', lineWidth: 1 },
                  { data: (style.series ?? []).filter((d) => d.ma5y != null).map((d) => ({ time: d.date, value: d.ma5y! })), color: '#f59e0b', lineWidth: 1 },
                ]}
                height={150}
              />
            </>
          ) : (
            <p className="text-sm text-gray-400">数据不足</p>
          )}
        </Section>
      </div>

      {/* ===== Row 4: 红利追踪 ===== */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

        {/* 股息率利差 */}
        <Section title="红利股息率利差" desc="中证红利股息率 - 10年期国债 — 利差越宽越有吸引力">
          {div.yield_spread && 'div_yield' in div.yield_spread ? (
            <>
              <div className="mb-3">
                <p className="text-2xl font-bold text-gray-900">{num(div.yield_spread.spread, 2)}%</p>
                <div className="mt-1"><SignalBadge signal={div.yield_spread.signal} text={div.yield_spread.signal_text} /></div>
              </div>
              <StatRow label="股息率" value={num(div.yield_spread.div_yield, 2)} unit="%" />
              <StatRow label="10Y国债" value={num(div.yield_spread.cn_bond, 2)} unit="%" />
              <LineChart
                series={[{ data: div.yield_spread.series.map((d) => ({ time: d.date, value: d.spread ?? 0 })), color: '#10b981', lineWidth: 1 }]}
                height={100}
                refLine={0}
              />
            </>
          ) : <p className="text-sm text-gray-400">数据不足</p>}
        </Section>

        {/* 红利相对全A */}
        <Section title="红利 40日相对收益" desc="中证红利 vs 中证全A — 过高不追，回落再买">
          {div.rel_return_40d && 'value' in div.rel_return_40d ? (
            <>
              <div className="mb-3">
                <p className="text-2xl font-bold text-gray-900">
                  {(div.rel_return_40d.value ?? 0) > 0 ? '+' : ''}{num(div.rel_return_40d.value, 1)}%
                </p>
                <div className="mt-1"><SignalBadge signal={div.rel_return_40d.signal} text={div.rel_return_40d.signal_text} /></div>
              </div>
              <LineChart
                series={[{ data: div.rel_return_40d.series.map((d) => ({ time: d.date, value: d.value })), color: '#f59e0b', lineWidth: 1 }]}
                height={100}
                refLine={0}
              />
              <p className="text-xs text-gray-300 mt-1">&gt;8% 过热 / &lt;-5% 机会</p>
            </>
          ) : <p className="text-sm text-gray-400">数据不足</p>}
        </Section>

        {/* 红利A vs 港 */}
        <Section title="红利 A 股 vs 港股" desc="中证红利 vs 港股通高股息 40日收益差">
          {div.ah_rel_return_40d && 'value' in div.ah_rel_return_40d ? (
            <>
              <div className="mb-3">
                <p className="text-2xl font-bold text-gray-900">
                  {(div.ah_rel_return_40d.value ?? 0) > 0 ? '+' : ''}{num(div.ah_rel_return_40d.value, 1)}%
                </p>
                <div className="mt-1"><SignalBadge signal={div.ah_rel_return_40d.signal} text={div.ah_rel_return_40d.signal_text} /></div>
              </div>
              <LineChart
                series={[{ data: div.ah_rel_return_40d.series.map((d) => ({ time: d.date, value: d.value })), color: '#ec4899', lineWidth: 1 }]}
                height={100}
                refLine={0}
              />
            </>
          ) : <p className="text-sm text-gray-400">数据不足</p>}
        </Section>
      </div>

      {/* ===== Row 5: 偏股基金3年滚动 + 换手率 ===== */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        {/* 偏股基金3年滚动 */}
        <Section
          title="偏股基金 3年滚动年化收益"
          desc="偏股混合基金指数 885001 — >30% 泡沫警示 / <-10% 底部区域"
        >
          {efr.available ? (
            <>
              <div className="flex items-center gap-3 mb-3">
                <p className="text-2xl font-bold text-gray-900">
                  {(efr.current_pct ?? 0) > 0 ? '+' : ''}{num(efr.current_pct, 1)}%
                </p>
                <SignalBadge signal={efr.signal ?? 'normal'} text={efr.signal_text ?? '-'} size="md" />
              </div>
              <LineChart
                series={[{
                  data: (efr.series ?? []).map((d) => ({ time: d.date, value: d.value })),
                  color: '#6366f1', lineWidth: 1,
                }]}
                height={160}
                refLine={0}
              />
              <p className="text-xs text-gray-300 mt-1.5">橙色区间: -10% ~ +30% 正常范围</p>
            </>
          ) : (
            <p className="text-sm text-gray-400">数据不足 (需要至少756个交易日数据)</p>
          )}
        </Section>

        {/* 换手率 + M2/PMI */}
        <Section
          title="市场活跃度 + 宏观"
          desc="全市场平均换手率 | M2同比 | 历史百分位"
        >
          <div className="space-y-1">
            <StatRow
              label="全A平均换手率"
              value={num(mt.value, 2)}
              unit="%"
              signal={mt.signal}
              signalText={mt.signal_text}
            />
            {mt.pct_rank != null && (
              <StatRow label="252日百分位" value={num(mt.pct_rank, 1)} unit="%" />
            )}
            <StatRow label="M2 同比增速" value={num(mp.m2_yoy.value, 1)} unit="%" />
            <StatRow label="制造业 PMI" value={num(mp.pmi_mfg.value, 1)} signal={mp.pmi_mfg.signal} signalText={mp.pmi_mfg.signal_text} />
          </div>
          {mt.available && (mt.series ?? []).length > 0 && (
            <div className="mt-3">
              <LineChart
                series={[{
                  data: (mt.series ?? []).map((d) => ({ time: d.date, value: d.value })),
                  color: '#06b6d4', lineWidth: 1,
                }]}
                height={120}
              />
              <p className="text-xs text-gray-300 mt-1">&lt;0.8% 冷清 / 0.8-3% 正常 / &gt;3% 活跃</p>
            </div>
          )}
        </Section>
      </div>

    </div>
  );
}
```

**Step 4: TypeScript check**

```bash
cd /Users/zhaobo/data0/person/myTrader/web && npx tsc --noEmit 2>&1 | head -30
```

Expected: 0 errors.

**Step 5: Commit**

```bash
git add web/src/components/market/ web/src/app/market/page.tsx
git commit -m "feat(frontend): market overview dashboard with charts and signal indicators"
```

---

## Task 7: End-to-end smoke test + final commit

**Step 1: Verify API is serving data**

```bash
curl -s http://localhost:8001/api/market-overview/summary | python3 -m json.tool | python3 -c "
import sys, json
d = json.load(sys.stdin)
for k in ['anchor_5y','stock_bond_spread','scale_rotation','dividend','macro_pulse']:
    v = d.get(k, {})
    print(k, ':', 'available=' + str(v.get('available', True)), '| keys:', list(v.keys())[:4])
"
```

**Step 2: Open browser**

Navigate to `http://localhost:3000/market` — expect dashboard to render with charts and stat cards.

**Step 3: Force cache refresh**

```bash
curl -s -X POST http://localhost:8001/api/market-overview/refresh | python3 -m json.tool | head -5
```

**Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete market overview dashboard (macro + rotation + dividend signals)"
```

---

## Appendix: Signal Reference Card (for indicator tooltip text)

| Indicator | Green signal | Yellow signal | Red signal |
|---|---|---|---|
| 五年之锚 | 偏离 < -10% (低估) | -10%~+20% (合理) | > +20% (高估) |
| 股债利差(内资) | > 3% | 1-3% | < 1% |
| 股债利差(外资) | > 2% | 0-2% | < 0% |
| 三棱镜 | 2-3 信号一致 | 1 信号 | 0 / 反向 |
| 红利股息率利差 | > 3% | 1-3% | < 1% |
| 红利40日超额 | < -5% (机会) | -5%~+8% | > +8% (过热) |
| QVIX | < 15 | 15-25 | > 35 |
| PMI | > 50 | 50 附近 | < 50 |
| 换手率 | — | 0.8-3% | > 3% 或 < 0.8% |
| 偏股基金3Y | < -10% (底部) | -10%~+30% | > 30% (泡沫) |
