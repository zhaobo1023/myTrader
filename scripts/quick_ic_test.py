# -*- coding: utf-8 -*-
"""Quick IC analysis for hard-tech vs all stocks"""
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pandas as pd
import numpy as np
from scipy.stats import spearmanr
from config.db import execute_query

INDUSTRIES = ['电子', '计算机', '通信', '电力设备', '机械设备', '国防军工', '医药生物', '汽车']
FORWARD_DAYS = 20


def main():
    # Find a date with enough forward trading days
    max_daily = execute_query('SELECT MAX(trade_date) as d FROM trade_stock_daily')[0]['d']
    # Need at least FORWARD_DAYS trading days before max_daily
    # Work backwards from max_daily to find a suitable date
    fwd_dates = execute_query(
        'SELECT DISTINCT trade_date FROM trade_stock_daily ORDER BY trade_date DESC LIMIT 40'
    )
    if len(fwd_dates) >= FORWARD_DAYS:
        target_end = str(fwd_dates[FORWARD_DAYS - 1]['trade_date'])
    else:
        target_end = str(max_daily)

    # Find a factor date on or before target_end that has data in all tables
    candidate = execute_query(f'''
        SELECT e.calc_date,
               (SELECT COUNT(*) FROM trade_stock_extended_factor WHERE calc_date = e.calc_date) as ext_cnt,
               (SELECT COUNT(*) FROM trade_stock_basic_factor WHERE calc_date = e.calc_date) as basic_cnt
        FROM (SELECT DISTINCT calc_date FROM trade_stock_extended_factor
              WHERE calc_date <= '{target_end}' ORDER BY calc_date DESC LIMIT 5) e
        ORDER BY e.calc_date DESC
    ''')

    target_date = None
    for r in candidate:
        if r['ext_cnt'] > 100 and r['basic_cnt'] > 100:
            target_date = str(r['calc_date'])
            break

    if not target_date:
        print('No suitable date found')
        return

    # Get hard-tech stock codes
    ph_ind = ', '.join(['%s'] * len(INDUSTRIES))
    ht_rows = execute_query(
        f'SELECT stock_code FROM trade_stock_basic WHERE industry IN ({ph_ind})',
        INDUSTRIES
    )
    ht_codes = [r['stock_code'] for r in ht_rows]
    print(f'Date: {target_date}, Hard-tech stocks: {len(ht_codes)}')

    # Build IN clause for queries
    ht_ph = ', '.join(['%s'] * len(ht_codes))

    # Load factors for hard-tech
    ext_ht = execute_query(
        f'SELECT stock_code, revenue_growth, gross_margin, roe_ttm '
        f'FROM trade_stock_extended_factor WHERE calc_date = %s AND stock_code IN ({ht_ph})',
        [target_date] + ht_codes
    )
    df_ht = pd.DataFrame(ext_ht)
    for col in ['revenue_growth', 'gross_margin', 'roe_ttm']:
        if col in df_ht.columns:
            df_ht[col] = pd.to_numeric(df_ht[col], errors='coerce')

    basic_ht = execute_query(
        f'SELECT stock_code, mom_20 FROM trade_stock_basic_factor WHERE calc_date = %s AND stock_code IN ({ht_ph})',
        [target_date] + ht_codes
    )
    if basic_ht:
        bdf = pd.DataFrame(basic_ht)
        bdf['mom_20'] = pd.to_numeric(bdf['mom_20'], errors='coerce')
        df_ht = df_ht.merge(bdf, on='stock_code', how='left')

    val_ht = execute_query(
        f'SELECT stock_code, market_cap FROM trade_stock_valuation_factor WHERE calc_date = %s AND stock_code IN ({ht_ph})',
        [target_date] + ht_codes
    )
    if val_ht:
        vdf = pd.DataFrame(val_ht)
        vdf['market_cap'] = pd.to_numeric(vdf['market_cap'], errors='coerce')
        df_ht = df_ht.merge(vdf, on='stock_code', how='left')

    # Load factors for all stocks
    ext_all = execute_query(
        'SELECT stock_code, revenue_growth, gross_margin, roe_ttm '
        'FROM trade_stock_extended_factor WHERE calc_date = %s',
        [target_date]
    )
    df_all = pd.DataFrame(ext_all)
    for col in ['revenue_growth', 'gross_margin', 'roe_ttm']:
        if col in df_all.columns:
            df_all[col] = pd.to_numeric(df_all[col], errors='coerce')

    # Forward returns (all stocks)
    end_ext = str(max_daily)
    fwd_rows = execute_query(
        'SELECT stock_code, trade_date, close_price FROM trade_stock_daily '
        'WHERE trade_date >= %s AND trade_date <= %s ORDER BY stock_code, trade_date',
        [target_date, end_ext]
    )
    fwd_df = pd.DataFrame(fwd_rows)
    fwd_df['trade_date'] = pd.to_datetime(fwd_df['trade_date'])
    fwd_df['close_price'] = pd.to_numeric(fwd_df['close_price'], errors='coerce')

    fwd_map = {}
    for code, group in fwd_df.groupby('stock_code'):
        group = group.sort_values('trade_date')
        if len(group) >= FORWARD_DAYS and group.iloc[0]['close_price'] > 0:
            # Forward return: buy at day 0, sell at day FORWARD_DAYS
            fwd_map[code] = group.iloc[FORWARD_DAYS - 1]['close_price'] / group.iloc[0]['close_price'] - 1

    df_ht['forward_20d'] = df_ht['stock_code'].map(fwd_map)
    df_all['forward_20d'] = df_all['stock_code'].map(fwd_map)

    n_ht = df_ht['forward_20d'].notna().sum()
    n_all = df_all['forward_20d'].notna().sum()

    # IC Analysis
    print(f'\n{"="*65}')
    print(f'  IC Analysis: {target_date} -> forward {FORWARD_DAYS}d')
    print(f'  Hard-tech: {n_ht} stocks | All: {n_all} stocks')
    print(f'{"="*65}')
    print(f'\n{"Factor":20s} | {"IC(HardTech)":>12s} | {"IC(All)":>12s} | {"Diff":>8s}')
    print('-' * 65)

    factors = ['revenue_growth', 'gross_margin', 'roe_ttm', 'mom_20', 'market_cap']
    for factor in factors:
        ic_ht = np.nan
        ic_all = np.nan

        if factor in df_ht.columns:
            v = df_ht[[factor, 'forward_20d']].dropna()
            if len(v) >= 30:
                ic_ht = spearmanr(v[factor], v['forward_20d'])[0]

        if factor in df_all.columns:
            v2 = df_all[[factor, 'forward_20d']].dropna()
            if len(v2) >= 30:
                ic_all = spearmanr(v2[factor], v2['forward_20d'])[0]

        ht_s = f'{ic_ht:.4f}' if not np.isnan(ic_ht) else 'N/A'
        all_s = f'{ic_all:.4f}' if not np.isnan(ic_all) else 'N/A'
        diff = f'{ic_ht - ic_all:+.4f}' if not np.isnan(ic_ht) and not np.isnan(ic_all) else ''
        print(f'{factor:20s} | {ht_s:>12s} | {all_s:>12s} | {diff:>8s}')

    print()

    # Also check if market_cap direction is different in HT vs All
    if 'market_cap' in df_ht.columns:
        v = df_ht[['market_cap', 'forward_20d']].dropna()
        if len(v) >= 30:
            ic = spearmanr(v['market_cap'], v['forward_20d'])[0]
            print(f'Note: market_cap IC in hard-tech = {ic:.4f}')
            print(f'  (Positive = large cap outperforms, Negative = small cap outperforms)')


if __name__ == '__main__':
    main()
