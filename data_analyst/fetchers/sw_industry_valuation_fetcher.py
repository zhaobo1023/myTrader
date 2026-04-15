# -*- coding: utf-8 -*-
"""
申万行业指数估值分位计算器

功能:
    1. 从 trade_stock_daily_basic + trade_stock_basic 聚合计算各申万一级行业的 PE/PB
    2. 计算 5 年历史分位，合成估值温度评分（0-100）
    3. 结果写入 sw_industry_valuation 表
    4. 支持单日计算和历史回填

估值计算方式（参考理杏仁）:
    - PE-TTM 市值加权: SUM(total_mv) / SUM(total_mv / pe_ttm)  即调和加权
    - PE-TTM 等权: 成分股 PE 等权（算术平均）
    - PE-TTM 中位数: 成分股 PE 中位数
    - PB 同理

估值温度评分（0-100）:
    score = (pe_pct_5y * 0.5 + pb_pct_5y * 0.3 + (1 - div_yield_pct_5y) * 0.2) * 100
    分数越低 = 估值越低
    < 30: 低估，30-70: 合理，> 70: 高估

用法:
    python -m data_analyst.fetchers.sw_industry_valuation_fetcher
    python -m data_analyst.fetchers.sw_industry_valuation_fetcher --backfill --start 20220101
    python -m data_analyst.fetchers.sw_industry_valuation_fetcher --date 20260414
"""
import argparse
import logging
import os
import sys
from datetime import date, timedelta
from typing import List, Optional

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from config.db import execute_query, execute_many, get_connection

logger = logging.getLogger('myTrader.sw_industry_valuation')
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

# ---------------------------------------------------------------------------
# 申万一级行业列表（31个，2021版）
# ---------------------------------------------------------------------------
SW_LEVEL1_LIST = [
    '农林牧渔', '基础化工', '钢铁', '有色金属', '电子', '汽车', '家用电器', '食品饮料',
    '纺织服饰', '轻工制造', '医药生物', '公用事业', '交通运输', '房地产', '商贸零售',
    '社会服务', '综合', '建筑材料', '建筑装饰', '电力设备', '国防军工', '计算机',
    '传媒', '通信', '银行', '非银金融', '煤炭', '石油石化', '环保', '美容护理', '机械设备',
]

# PE 有效范围过滤（去除亏损/极端估值）
PE_MIN = 0
PE_MAX = 300
PB_MIN = 0
PB_MAX = 50

# 估值温度阈值
SCORE_LOW = 30    # 低于此值为"低估"
SCORE_HIGH = 70   # 高于此值为"高估"

# 历史分位计算窗口（交易日数）
WINDOW_5Y = 250 * 5    # 约 5 年
WINDOW_10Y = 250 * 10  # 约 10 年


# ---------------------------------------------------------------------------
# 数据库操作
# ---------------------------------------------------------------------------

INSERT_SQL = """
INSERT INTO sw_industry_valuation
    (trade_date, sw_code, sw_name, sw_level, pe_ttm, pe_ttm_eq, pe_ttm_med,
     pb, pb_med, pe_pct_5y, pb_pct_5y, pe_pct_10y, pb_pct_10y,
     valuation_score, valuation_label)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    pe_ttm = VALUES(pe_ttm),
    pe_ttm_eq = VALUES(pe_ttm_eq),
    pe_ttm_med = VALUES(pe_ttm_med),
    pb = VALUES(pb),
    pb_med = VALUES(pb_med),
    pe_pct_5y = VALUES(pe_pct_5y),
    pb_pct_5y = VALUES(pb_pct_5y),
    pe_pct_10y = VALUES(pe_pct_10y),
    pb_pct_10y = VALUES(pb_pct_10y),
    valuation_score = VALUES(valuation_score),
    valuation_label = VALUES(valuation_label)
"""


def get_latest_date() -> Optional[date]:
    rows = execute_query(
        'SELECT MAX(trade_date) as d FROM sw_industry_valuation',
        env='online'
    )
    if rows and rows[0]['d']:
        return rows[0]['d']
    return None


def get_trade_dates(start: str, end: str) -> List[str]:
    """从 trade_stock_daily_basic 获取交易日列表"""
    rows = execute_query(
        'SELECT DISTINCT trade_date FROM trade_stock_daily_basic WHERE trade_date >= %s AND trade_date <= %s ORDER BY trade_date',
        (start, end),
        env='online'
    )
    return [r['trade_date'].strftime('%Y-%m-%d') for r in rows]


# ---------------------------------------------------------------------------
# 单日行业 PE/PB 计算
# ---------------------------------------------------------------------------

def calc_daily_industry_valuation(trade_date: str) -> pd.DataFrame:
    """
    计算某交易日各申万一级行业的 PE/PB。

    Returns DataFrame with columns:
        sw_name, stock_cnt, total_mv, pe_ttm, pe_ttm_eq, pe_ttm_med, pb, pb_med
    """
    sql = """
    SELECT
        b.sw_level1 AS sw_name,
        d.pe_ttm,
        d.pb,
        CAST(d.total_mv AS DECIMAL(20,4)) AS total_mv
    FROM trade_stock_daily_basic d
    JOIN trade_stock_basic b
        ON d.stock_code COLLATE utf8mb4_unicode_ci = b.stock_code COLLATE utf8mb4_unicode_ci
    WHERE d.trade_date = %s
      AND b.sw_level1 IS NOT NULL
      AND d.pe_ttm IS NOT NULL
      AND d.pb IS NOT NULL
      AND d.total_mv IS NOT NULL
    """
    rows = execute_query(sql, (trade_date,), env='online')
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df['pe_ttm'] = pd.to_numeric(df['pe_ttm'], errors='coerce')
    df['pb'] = pd.to_numeric(df['pb'], errors='coerce')
    df['total_mv'] = pd.to_numeric(df['total_mv'], errors='coerce')

    # 过滤有效范围
    df_pe = df[(df['pe_ttm'] > PE_MIN) & (df['pe_ttm'] < PE_MAX)]
    df_pb = df[(df['pb'] > PB_MIN) & (df['pb'] < PB_MAX)]

    results = []
    for industry in SW_LEVEL1_LIST:
        sub_pe = df_pe[df_pe['sw_name'] == industry]
        sub_pb = df_pb[df_pb['sw_name'] == industry]

        if sub_pe.empty and sub_pb.empty:
            continue

        row = {'sw_name': industry}

        # PE 计算
        if not sub_pe.empty:
            mv = sub_pe['total_mv']
            pe = sub_pe['pe_ttm']
            row['stock_cnt'] = len(sub_pe)
            row['total_mv'] = float(mv.sum())
            # 市值加权（调和平均）
            mv_sum = mv.sum()
            harmonic_denom = (mv / pe).sum()
            row['pe_ttm'] = float(mv_sum / harmonic_denom) if harmonic_denom > 0 else None
            # 等权（算术平均）
            row['pe_ttm_eq'] = float(pe.mean())
            # 中位数
            row['pe_ttm_med'] = float(pe.median())
        else:
            row['stock_cnt'] = 0
            row['total_mv'] = 0
            row['pe_ttm'] = None
            row['pe_ttm_eq'] = None
            row['pe_ttm_med'] = None

        # PB 计算
        if not sub_pb.empty:
            mv_pb = sub_pb['total_mv']
            pb = sub_pb['pb']
            mv_sum_pb = mv_pb.sum()
            harmonic_pb = (mv_pb / pb).sum()
            row['pb'] = float(mv_sum_pb / harmonic_pb) if harmonic_pb > 0 else None
            row['pb_med'] = float(pb.median())
        else:
            row['pb'] = None
            row['pb_med'] = None

        results.append(row)

    return pd.DataFrame(results)


# ---------------------------------------------------------------------------
# 历史分位计算
# ---------------------------------------------------------------------------

def calc_percentile(series: pd.Series, window: int) -> pd.Series:
    """
    对时间序列滚动计算历史分位（当前值在过去 window 期数据中的分位）。
    分位值 0-1。
    """
    def _pct(x):
        if len(x) < 2:
            return np.nan
        current = x.iloc[-1]
        if pd.isna(current):
            return np.nan
        return (x < current).sum() / len(x)

    return series.rolling(window=window, min_periods=max(20, window // 10)).apply(_pct, raw=False)


def load_history_for_percentile(industry: str) -> pd.DataFrame:
    """
    从 sw_industry_valuation 加载某行业的完整历史 PE/PB，用于分位计算。
    """
    rows = execute_query(
        'SELECT trade_date, pe_ttm, pb FROM sw_industry_valuation WHERE sw_name = %s ORDER BY trade_date',
        (industry,),
        env='online'
    )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df['pe_ttm'] = pd.to_numeric(df['pe_ttm'], errors='coerce')
    df['pb'] = pd.to_numeric(df['pb'], errors='coerce')
    return df.set_index('trade_date')


def calc_valuation_score(pe_pct: float, pb_pct: float) -> float:
    """综合估值温度：PE分位权重0.5，PB分位权重0.5（无股息率数据时简化）"""
    if pe_pct is None and pb_pct is None:
        return None
    if pe_pct is None:
        return round(pb_pct * 100, 1)
    if pb_pct is None:
        return round(pe_pct * 100, 1)
    return round((pe_pct * 0.6 + pb_pct * 0.4) * 100, 1)


def get_label(score: float) -> str:
    if score is None:
        return ''
    if score < SCORE_LOW:
        return '低估'
    if score > SCORE_HIGH:
        return '高估'
    return '合理'


# ---------------------------------------------------------------------------
# 写入数据库
# ---------------------------------------------------------------------------

def save_daily(trade_date: str, df_val: pd.DataFrame, percentiles: dict) -> int:
    """
    保存一天的行业估值数据。

    percentiles: {industry: {'pe_pct_5y': float, 'pb_pct_5y': float, ...}}
    """
    if df_val.empty:
        return 0

    rows = []
    for _, row in df_val.iterrows():
        name = row['sw_name']
        pct = percentiles.get(name, {})
        pe_pct_5y = pct.get('pe_pct_5y')
        pb_pct_5y = pct.get('pb_pct_5y')
        pe_pct_10y = pct.get('pe_pct_10y')
        pb_pct_10y = pct.get('pb_pct_10y')

        score = calc_valuation_score(pe_pct_5y, pb_pct_5y)
        label = get_label(score)

        rows.append((
            trade_date,
            '',        # sw_code 暂时为空，申万行业名即可唯一标识
            name,
            1,         # sw_level = 1
            row.get('pe_ttm'),
            row.get('pe_ttm_eq'),
            row.get('pe_ttm_med'),
            row.get('pb'),
            row.get('pb_med'),
            pe_pct_5y,
            pb_pct_5y,
            pe_pct_10y,
            pb_pct_10y,
            score,
            label,
        ))

    if rows:
        conn = get_connection(env='online')
        cursor = conn.cursor()
        cursor.executemany(INSERT_SQL, rows)
        conn.commit()
        cursor.close()
        conn.close()

    return len(rows)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def run_single_date(trade_date: str) -> dict:
    """
    计算单日各行业估值并写入数据库。
    分位基于当日之前的历史数据（包含当日）重新算。
    """
    logger.info('计算 %s 行业估值...', trade_date)

    # 1. 计算当日 PE/PB
    df_val = calc_daily_industry_valuation(trade_date)
    if df_val.empty:
        logger.warning('%s 无数据', trade_date)
        return {'date': trade_date, 'industries': 0}

    # 2. 先写入当日（不含分位），然后从历史数据计算分位
    # 注：分位需要历史数据，所以先 upsert 当日基础值
    rows_base = []
    for _, row in df_val.iterrows():
        rows_base.append((
            trade_date, '', row['sw_name'], 1,
            row.get('pe_ttm'), row.get('pe_ttm_eq'), row.get('pe_ttm_med'),
            row.get('pb'), row.get('pb_med'),
            None, None, None, None, None, ''
        ))
    if rows_base:
        conn = get_connection(env='online')
        cursor = conn.cursor()
        cursor.executemany(INSERT_SQL, rows_base)
        conn.commit()
        cursor.close()
        conn.close()

    # 3. 计算各行业分位
    percentiles = {}
    for industry in df_val['sw_name'].tolist():
        hist = load_history_for_percentile(industry)
        if hist.empty or len(hist) < 2:
            continue

        pe_series = hist['pe_ttm'].dropna()
        pb_series = hist['pb'].dropna()

        if len(pe_series) >= 2:
            pe_pct_5y = calc_percentile(pe_series, WINDOW_5Y)
            pe_pct_10y = calc_percentile(pe_series, WINDOW_10Y)
            last_pe_5y = float(pe_pct_5y.iloc[-1]) if not pe_pct_5y.empty and not pd.isna(pe_pct_5y.iloc[-1]) else None
            last_pe_10y = float(pe_pct_10y.iloc[-1]) if not pe_pct_10y.empty and not pd.isna(pe_pct_10y.iloc[-1]) else None
        else:
            last_pe_5y = last_pe_10y = None

        if len(pb_series) >= 2:
            pb_pct_5y = calc_percentile(pb_series, WINDOW_5Y)
            pb_pct_10y = calc_percentile(pb_series, WINDOW_10Y)
            last_pb_5y = float(pb_pct_5y.iloc[-1]) if not pb_pct_5y.empty and not pd.isna(pb_pct_5y.iloc[-1]) else None
            last_pb_10y = float(pb_pct_10y.iloc[-1]) if not pb_pct_10y.empty and not pd.isna(pb_pct_10y.iloc[-1]) else None
        else:
            last_pb_5y = last_pb_10y = None

        percentiles[industry] = {
            'pe_pct_5y': last_pe_5y,
            'pb_pct_5y': last_pb_5y,
            'pe_pct_10y': last_pe_10y,
            'pb_pct_10y': last_pb_10y,
        }

    # 4. 更新分位和评分
    update_sql = """
    UPDATE sw_industry_valuation
    SET pe_pct_5y=%s, pb_pct_5y=%s, pe_pct_10y=%s, pb_pct_10y=%s,
        valuation_score=%s, valuation_label=%s
    WHERE trade_date=%s AND sw_name=%s
    """
    conn = get_connection(env='online')
    cursor = conn.cursor()
    for industry, pct in percentiles.items():
        score = calc_valuation_score(pct.get('pe_pct_5y'), pct.get('pb_pct_5y'))
        label = get_label(score)
        cursor.execute(update_sql, (
            pct.get('pe_pct_5y'), pct.get('pb_pct_5y'),
            pct.get('pe_pct_10y'), pct.get('pb_pct_10y'),
            score, label,
            trade_date, industry,
        ))
    conn.commit()
    cursor.close()
    conn.close()

    logger.info('%s 完成: %d 个行业', trade_date, len(df_val))
    return {'date': trade_date, 'industries': len(df_val)}


def run_backfill(start_date: str, end_date: str = None) -> dict:
    """
    批量回填历史数据（高效版）。

    策略：
    1. 按日期顺序计算各行业 PE/PB，批量 INSERT（不含分位）
    2. 全部写完后，一次性从 DB 加载全量历史，向量化计算所有日期的分位并批量 UPDATE
    """
    if end_date is None:
        end_date = date.today().strftime('%Y-%m-%d')

    logger.info('回填历史数据: %s ~ %s', start_date, end_date)
    trade_dates = get_trade_dates(start_date, end_date)
    logger.info('共 %d 个交易日', len(trade_dates))

    # --- Step 1: 计算并插入基础 PE/PB（不含分位）---
    all_rows = []
    for i, td in enumerate(trade_dates):
        df_val = calc_daily_industry_valuation(td)
        if df_val.empty:
            continue
        for _, row in df_val.iterrows():
            all_rows.append((
                td, '', row['sw_name'], 1,
                row.get('pe_ttm'), row.get('pe_ttm_eq'), row.get('pe_ttm_med'),
                row.get('pb'), row.get('pb_med'),
                None, None, None, None, None, ''
            ))
        if (i + 1) % 50 == 0:
            logger.info('PE/PB 计算进度: %d/%d', i + 1, len(trade_dates))

    if all_rows:
        conn = get_connection(env='online')
        cursor = conn.cursor()
        cursor.executemany(INSERT_SQL, all_rows)
        conn.commit()
        cursor.close()
        conn.close()
        logger.info('写入基础数据 %d 条', len(all_rows))

    # --- Step 2: 批量计算分位并 UPDATE ---
    logger.info('开始批量计算分位...')
    _batch_update_percentiles()

    logger.info('回填完成: %d 条记录', len(all_rows))
    return {'total_records': len(all_rows), 'dates': len(trade_dates)}


def _batch_update_percentiles():
    """
    一次性加载全量历史，向量化计算所有日期的 5年/10年 PE/PB 分位，批量 UPDATE。
    """
    # 加载全量数据
    rows = execute_query(
        'SELECT trade_date, sw_name, pe_ttm, pb FROM sw_industry_valuation ORDER BY sw_name, trade_date',
        env='online'
    )
    if not rows:
        return

    df = pd.DataFrame(rows)
    df['trade_date'] = pd.to_datetime(df['trade_date'])
    df['pe_ttm'] = pd.to_numeric(df['pe_ttm'], errors='coerce')
    df['pb'] = pd.to_numeric(df['pb'], errors='coerce')

    update_sql = """
    UPDATE sw_industry_valuation
    SET pe_pct_5y=%s, pb_pct_5y=%s, pe_pct_10y=%s, pb_pct_10y=%s,
        valuation_score=%s, valuation_label=%s
    WHERE trade_date=%s AND sw_name=%s
    """

    update_rows = []
    for industry in df['sw_name'].unique():
        sub = df[df['sw_name'] == industry].sort_values('trade_date').copy()
        sub = sub.set_index('trade_date')

        pe = sub['pe_ttm']
        pb = sub['pb']

        pe_pct5 = calc_percentile(pe, WINDOW_5Y)
        pe_pct10 = calc_percentile(pe, WINDOW_10Y)
        pb_pct5 = calc_percentile(pb, WINDOW_5Y)
        pb_pct10 = calc_percentile(pb, WINDOW_10Y)

        for td in sub.index:
            td_str = td.strftime('%Y-%m-%d')
            pp5 = float(pe_pct5.loc[td]) if td in pe_pct5.index and not pd.isna(pe_pct5.loc[td]) else None
            pp10 = float(pe_pct10.loc[td]) if td in pe_pct10.index and not pd.isna(pe_pct10.loc[td]) else None
            bp5 = float(pb_pct5.loc[td]) if td in pb_pct5.index and not pd.isna(pb_pct5.loc[td]) else None
            bp10 = float(pb_pct10.loc[td]) if td in pb_pct10.index and not pd.isna(pb_pct10.loc[td]) else None

            score = calc_valuation_score(pp5, bp5)
            label = get_label(score)
            update_rows.append((pp5, bp5, pp10, bp10, score, label, td_str, industry))

    if update_rows:
        conn = get_connection(env='online')
        cursor = conn.cursor()
        # 分批提交，每批 500 条
        batch_size = 500
        for i in range(0, len(update_rows), batch_size):
            cursor.executemany(update_sql, update_rows[i:i + batch_size])
            conn.commit()
        cursor.close()
        conn.close()
        logger.info('分位批量更新完成: %d 条', len(update_rows))


def run_daily() -> dict:
    """每日增量更新（调度器调用入口）"""
    latest = get_latest_date()
    today = date.today()

    if latest is None:
        # 首次运行，回填最近 1 年
        start = (today - timedelta(days=365)).strftime('%Y-%m-%d')
        logger.info('首次运行，回填 1 年历史: %s', start)
        return run_backfill(start)

    if latest >= today:
        logger.info('数据已是最新 (%s)', latest)
        return {'status': 'up_to_date'}

    # 增量更新
    start = (latest + timedelta(days=1)).strftime('%Y-%m-%d')
    end = today.strftime('%Y-%m-%d')
    trade_dates = get_trade_dates(start, end)

    results = {}
    for td in trade_dates:
        results[td] = run_single_date(td)

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='申万行业估值分位计算')
    parser.add_argument('--date', type=str, help='计算指定日期 (YYYYMMDD 或 YYYY-MM-DD)')
    parser.add_argument('--backfill', action='store_true', help='回填历史数据')
    parser.add_argument('--start', type=str, default='20220101', help='回填起始日期 (YYYYMMDD)')
    parser.add_argument('--end', type=str, default=None, help='回填结束日期 (YYYYMMDD)')
    args = parser.parse_args()

    if args.date:
        td = args.date.replace('-', '')
        td_fmt = '{}-{}-{}'.format(td[:4], td[4:6], td[6:])
        result = run_single_date(td_fmt)
        print(result)
    elif args.backfill:
        start = '{}-{}-{}'.format(args.start[:4], args.start[4:6], args.start[6:])
        end = None
        if args.end:
            end = '{}-{}-{}'.format(args.end[:4], args.end[4:6], args.end[6:])
        result = run_backfill(start, end)
        print(result)
    else:
        result = run_daily()
        print(result)
