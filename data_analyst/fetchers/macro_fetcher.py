# -*- coding: utf-8 -*-
"""
宏观数据拉取器 (Macro Data Fetcher)

功能:
    1. 使用 AkShare 拉取外部宏观数据
    2. 支持增量更新
    3. 存入 MySQL 的 macro_data 表

数据源:
    - WTI原油价格: futures_foreign_hist(symbol='CL')
    - 黄金价格: futures_foreign_hist(symbol='XAU')
    - 中国波指(类VIX): index_option_50etf_qvix()
    - 北向资金: stock_hsgt_hist_em(symbol='北向资金')
    - 中证全A/沪深300/中证500/中证1000/中证红利等: index_zh_a_hist
    - 沪深300 PE/股息率: stock_zh_index_value_csindex
    - 中国/美国 10Y 国债: bond_zh_us_rate
    - M2同比增速: macro_china_m2_yearly
    - 制造业PMI: macro_china_pmi
    - AH溢价指数: index_zh_a_hist(symbol='000821')

运行:
    python data_analyst/fetchers/macro_fetcher.py

环境:
    pip install akshare
"""
import re
import sys
import os
from datetime import date, timedelta
from typing import Optional, Tuple

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config.db import get_connection, execute_query, execute_many, execute_dual_many

# 尝试导入 akshare
try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False
    print("警告: AKShare 未安装，请运行 pip install akshare")


# ============================================================
# 配置
# ============================================================
MACRO_DATA_START = '20200101'  # 默认起始日期


# ============================================================
# 数据源配置
# ============================================================
# 每个指标的配置: (名称, 数据源类型, 参数)
MACRO_INDICATORS = {
    'wti_oil': {
        'name': 'WTI原油',
        'source': 'futures_foreign_hist',
        'params': {'symbol': 'CL'},
        'value_column': 'close',  # 取收盘价
        'date_column': 'date',
    },
    'gold': {
        'name': '黄金',
        'source': 'futures_foreign_hist',
        'params': {'symbol': 'XAU'},
        'value_column': 'close',
        'date_column': 'date',
    },
    'qvix': {
        'name': '中国波指(50ETF期权VIX)',
        'source': 'index_option_50etf_qvix',
        'params': {},
        'value_column': 'close',
        'date_column': 'date',
    },
    'north_flow': {
        'name': '北向资金净流入',
        'source': 'stock_hsgt_hist_em',
        'params': {'symbol': '北向资金'},
        'value_column': '当日成交净买额',
        'date_column': '日期',
    },
    'idx_all_a': {
        'name': '中证全A',
        'source': 'index_zh_a_hist',
        'params': {'symbol': '000985'},
    },
    'idx_csi300': {
        'name': '沪深300',
        'source': 'index_zh_a_hist',
        'params': {'symbol': '000300'},
    },
    'idx_csi500': {
        'name': '中证500',
        'source': 'index_zh_a_hist',
        'params': {'symbol': '000905'},
    },
    'idx_csi1000': {
        'name': '中证1000',
        'source': 'index_zh_a_hist',
        'params': {'symbol': '000852'},
    },
    'idx_dividend': {
        'name': '中证红利',
        'source': 'index_zh_a_hist',
        'params': {'symbol': '000922'},
    },
    'idx_growth300': {
        'name': '沪深300成长',
        'source': 'index_zh_a_hist',
        'params': {'symbol': '000918'},
    },
    'idx_value300': {
        'name': '沪深300价值',
        'source': 'index_zh_a_hist',
        'params': {'symbol': '000919'},
    },
    'idx_hk_dividend': {
        'name': '港股通高股息',
        'source': 'index_zh_a_hist',
        'params': {'symbol': '930914'},
    },
    'idx_equity_fund': {
        'name': '偏股混合基金指数',
        'source': 'index_zh_a_hist',
        'params': {'symbol': '885001'},
    },
    'ah_premium': {
        'name': 'AH溢价指数',
        'source': 'index_zh_a_hist',
        'params': {'symbol': '000821'},
    },
    'pe_csi300': {
        'name': '沪深300 PE',
        'source': 'stock_zh_index_value_csindex',
        'params': {'symbol': '000300'},
    },
    'div_yield_csi300': {
        'name': '沪深300股息率',
        'source': 'stock_zh_index_value_csindex',
        'params': {'symbol': '000300'},
    },
    'cn_10y_bond': {
        'name': '中国10Y国债',
        'source': 'bond_zh_us_rate',
        'params': {},
    },
    'us_10y_bond': {
        'name': '美国10Y国债',
        'source': 'bond_zh_us_rate',
        'params': {},
    },
    'm2_yoy': {
        'name': 'M2同比增速',
        'source': 'macro_china_m2_yearly',
        'params': {},
    },
    'pmi_mfg': {
        'name': '制造业PMI',
        'source': 'macro_china_pmi',
        'params': {},
    },
}


# ============================================================
# 数据库操作
# ============================================================

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS macro_data (
    date DATE NOT NULL COMMENT '日期',
    indicator VARCHAR(50) NOT NULL COMMENT '指标代码',
    value DECIMAL(20, 4) COMMENT '数值',
    PRIMARY KEY (date, indicator),
    INDEX idx_indicator (indicator),
    INDEX idx_date (date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='宏观数据表';
"""


def ensure_table_exists():
    """确保 macro_data 表存在"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(CREATE_TABLE_SQL)
    conn.commit()
    cursor.close()
    conn.close()


def get_latest_date(indicator: str) -> Optional[str]:
    """
    获取某个指标在数据库中的最新日期

    Args:
        indicator: 指标代码

    Returns:
        最新日期字符串 (YYYY-MM-DD) 或 None
    """
    rows = execute_query(
        "SELECT MAX(date) as max_date FROM macro_data WHERE indicator = %s",
        (indicator,)
    )
    if rows and rows[0]['max_date']:
        return rows[0]['max_date'].strftime('%Y-%m-%d')
    return None


# ============================================================
# 数据拉取函数
# ============================================================

def fetch_wti_oil(start_date: str) -> pd.DataFrame:
    """
    拉取 WTI 原油价格

    Args:
        start_date: 起始日期 YYYYMMDD

    Returns:
        DataFrame with columns: [date, value]
    """
    if not HAS_AKSHARE:
        raise RuntimeError("AKShare 未安装")

    df = ak.futures_foreign_hist(symbol='CL')
    if df is None or df.empty:
        return pd.DataFrame()

    # 确保日期格式一致
    df['date'] = pd.to_datetime(df['date'])
    df = df[['date', 'close']].rename(columns={'close': 'value'})

    # 过滤日期
    start_dt = pd.to_datetime(start_date)
    df = df[df['date'] >= start_dt]

    return df


def fetch_gold(start_date: str) -> pd.DataFrame:
    """
    拉取黄金价格

    Args:
        start_date: 起始日期 YYYYMMDD

    Returns:
        DataFrame with columns: [date, value]
    """
    if not HAS_AKSHARE:
        raise RuntimeError("AKShare 未安装")

    df = ak.futures_foreign_hist(symbol='XAU')
    if df is None or df.empty:
        return pd.DataFrame()

    df['date'] = pd.to_datetime(df['date'])
    df = df[['date', 'close']].rename(columns={'close': 'value'})

    start_dt = pd.to_datetime(start_date)
    df = df[df['date'] >= start_dt]

    return df


def fetch_qvix(start_date: str) -> pd.DataFrame:
    """
    拉取中国波指(50ETF期权波动率指数)

    Args:
        start_date: 起始日期 YYYYMMDD

    Returns:
        DataFrame with columns: [date, value]
    """
    if not HAS_AKSHARE:
        raise RuntimeError("AKShare 未安装")

    df = ak.index_option_50etf_qvix()
    if df is None or df.empty:
        return pd.DataFrame()

    df['date'] = pd.to_datetime(df['date'])
    df = df[['date', 'close']].rename(columns={'close': 'value'})

    start_dt = pd.to_datetime(start_date)
    df = df[df['date'] >= start_dt]

    return df


def fetch_north_flow(start_date: str) -> pd.DataFrame:
    """
    拉取北向资金净流入

    Args:
        start_date: 起始日期 YYYYMMDD

    Returns:
        DataFrame with columns: [date, value]
    """
    if not HAS_AKSHARE:
        raise RuntimeError("AKShare 未安装")

    df = ak.stock_hsgt_hist_em(symbol='北向资金')
    if df is None or df.empty:
        return pd.DataFrame()

    df['日期'] = pd.to_datetime(df['日期'])
    df = df[['日期', '当日成交净买额']].rename(columns={'日期': 'date', '当日成交净买额': 'value'})

    start_dt = pd.to_datetime(start_date)
    df = df[df['date'] >= start_dt]

    return df


def fetch_index_daily(symbol: str, start_date: str) -> pd.DataFrame:
    """
    通用指数日线数据拉取，使用 ak.index_zh_a_hist

    Args:
        symbol: 指数代码，如 '000985'
        start_date: 起始日期，YYYY-MM-DD 或 YYYYMMDD 格式

    Returns:
        DataFrame with columns: [date, value]
    """
    if not HAS_AKSHARE:
        raise RuntimeError("AKShare 未安装")

    # 统一转换为 YYYYMMDD
    start_date_no_dash = start_date.replace('-', '')

    df = ak.index_zh_a_hist(
        symbol=symbol,
        period='daily',
        start_date=start_date_no_dash,
        end_date='99991231',
    )
    if df is None or df.empty:
        return pd.DataFrame()

    df['日期'] = pd.to_datetime(df['日期'])
    df = df[['日期', '收盘']].rename(columns={'日期': 'date', '收盘': 'value'})

    return df


def _make_index_fetcher(symbol: str):
    """
    工厂函数：返回一个以 start_date 为参数的指数拉取函数

    Args:
        symbol: 指数代码

    Returns:
        function(start_date: str) -> pd.DataFrame
    """
    def fetcher(start_date: str) -> pd.DataFrame:
        return fetch_index_daily(symbol, start_date)
    fetcher.__name__ = 'fetch_index_{}'.format(symbol)
    return fetcher


def fetch_csi300_valuation(start_date: str) -> pd.DataFrame:
    """
    拉取沪深300 PE 和股息率（来自 ak.stock_zh_index_value_csindex）

    Args:
        start_date: 起始日期，YYYY-MM-DD 或 YYYYMMDD 格式

    Returns:
        DataFrame with columns: [date, pe, div_yield]
    """
    if not HAS_AKSHARE:
        raise RuntimeError("AKShare 未安装")

    df = ak.stock_zh_index_value_csindex(symbol='000300')
    if df is None or df.empty:
        return pd.DataFrame()

    df['日期'] = pd.to_datetime(df['日期'])

    start_dt = pd.to_datetime(start_date.replace('-', ''), format='%Y%m%d')
    df = df[df['日期'] >= start_dt]

    df = df[['日期', '市盈率1', '股息率1']].rename(
        columns={'日期': 'date', '市盈率1': 'pe', '股息率1': 'div_yield'}
    )

    df['pe'] = pd.to_numeric(df['pe'], errors='coerce')
    df['div_yield'] = pd.to_numeric(df['div_yield'], errors='coerce')

    return df.reset_index(drop=True)


def fetch_bond_yields(start_date: str) -> pd.DataFrame:
    """
    拉取中国和美国 10 年期国债收益率

    Args:
        start_date: 起始日期，YYYY-MM-DD 或 YYYYMMDD 格式

    Returns:
        DataFrame with columns: [date, cn_10y, us_10y]
    """
    if not HAS_AKSHARE:
        raise RuntimeError("AKShare 未安装")

    start_date_no_dash = start_date.replace('-', '')

    df = ak.bond_zh_us_rate(start_date=start_date_no_dash)
    if df is None or df.empty:
        return pd.DataFrame()

    df['日期'] = pd.to_datetime(df['日期'])

    cn_col = '中国国债收益率10年'
    us_col = '美国国债收益率10年'

    df = df[['日期', cn_col, us_col]].rename(
        columns={'日期': 'date', cn_col: 'cn_10y', us_col: 'us_10y'}
    )

    df['cn_10y'] = pd.to_numeric(df['cn_10y'], errors='coerce')
    df['us_10y'] = pd.to_numeric(df['us_10y'], errors='coerce')

    # 去掉两列均为 NaN 的行
    df = df.dropna(subset=['cn_10y', 'us_10y'], how='all')

    return df.reset_index(drop=True)


def fetch_m2_yoy(start_date: str) -> pd.DataFrame:
    """
    拉取 M2 同比增速（月度）

    AKShare macro_china_m2_yearly 返回列: 商品, 日期, 今值, 预测值, 前值
    使用 '日期' 列作为日期，'今值' 列作为数值。

    Args:
        start_date: 起始日期，YYYY-MM-DD 或 YYYYMMDD 格式（仅用于过滤）

    Returns:
        DataFrame with columns: [date, value]
    """
    if not HAS_AKSHARE:
        raise RuntimeError("AKShare 未安装")

    df = ak.macro_china_m2_yearly()
    if df is None or df.empty:
        return pd.DataFrame()

    # 实际列名为 '日期'，而非 '月份'
    date_col = '日期' if '日期' in df.columns else '月份'
    df[date_col] = pd.to_datetime(df[date_col])
    df = df[[date_col, '今值']].rename(columns={date_col: 'date', '今值': 'value'})
    df['value'] = pd.to_numeric(df['value'], errors='coerce')

    start_dt = pd.to_datetime(start_date.replace('-', ''), format='%Y%m%d')
    df = df[df['date'] >= start_dt]

    return df.reset_index(drop=True)


def fetch_pmi_mfg(start_date: str) -> pd.DataFrame:
    """
    拉取制造业 PMI（月度）

    AKShare macro_china_pmi 返回列: 月份(格式如 '2026年03月份'), 制造业-指数, ...
    需要将 '2026年03月份' 格式转换为标准日期。

    Args:
        start_date: 起始日期，YYYY-MM-DD 或 YYYYMMDD 格式（仅用于过滤）

    Returns:
        DataFrame with columns: [date, value]
    """
    if not HAS_AKSHARE:
        raise RuntimeError("AKShare 未安装")

    df = ak.macro_china_pmi()
    if df is None or df.empty:
        return pd.DataFrame()

    # 将 '2026年03月份' 格式解析为日期
    # 先用正则提取年份和月份数字，再拼接成标准格式
    def parse_cn_month(s):
        m = re.match(r'(\d{4})年(\d{1,2})月', str(s))
        if m:
            return '{}-{:02d}-01'.format(m.group(1), int(m.group(2)))
        return None

    df['_date_str'] = df['月份'].apply(parse_cn_month)
    df = df.dropna(subset=['_date_str'])
    df['_date_str'] = pd.to_datetime(df['_date_str'])

    # 优先使用 '制造业-指数' 列，若不存在则使用月份之后的第一个数值列
    target_col = None
    if '制造业-指数' in df.columns:
        target_col = '制造业-指数'
    else:
        for col in df.columns:
            if col not in ('月份', '_date_str'):
                try:
                    pd.to_numeric(df[col], errors='raise')
                    target_col = col
                    break
                except (ValueError, TypeError):
                    continue

    if target_col is None:
        return pd.DataFrame()

    df = df[['_date_str', target_col]].rename(columns={'_date_str': 'date', target_col: 'value'})
    df['value'] = pd.to_numeric(df['value'], errors='coerce')

    start_dt = pd.to_datetime(start_date.replace('-', ''), format='%Y%m%d')
    df = df[df['date'] >= start_dt]

    return df.reset_index(drop=True)


# ============================================================
# 数据拉取映射
# ============================================================
FETCH_FUNCTIONS = {
    'wti_oil': fetch_wti_oil,
    'gold': fetch_gold,
    'qvix': fetch_qvix,
    'north_flow': fetch_north_flow,
}

# 注册指数日线拉取函数（使用闭包工厂避免循环变量捕获问题）
for _sym_key, _sym_code in [
    ('idx_all_a', '000985'),
    ('idx_csi300', '000300'),
    ('idx_csi500', '000905'),
    ('idx_csi1000', '000852'),
    ('idx_dividend', '000922'),
    ('idx_growth300', '000918'),
    ('idx_value300', '000919'),
    ('idx_hk_dividend', '930914'),
    ('idx_equity_fund', '885001'),
    ('ah_premium', '000821'),
]:
    FETCH_FUNCTIONS[_sym_key] = _make_index_fetcher(_sym_code)

FETCH_FUNCTIONS['m2_yoy'] = fetch_m2_yoy
FETCH_FUNCTIONS['pmi_mfg'] = fetch_pmi_mfg


# ============================================================
# 保存数据
# ============================================================

INSERT_SQL = """
    INSERT INTO macro_data (date, indicator, value)
    VALUES (%s, %s, %s)
    ON DUPLICATE KEY UPDATE value = VALUES(value)
"""


def save_data(indicator: str, df: pd.DataFrame) -> int:
    """
    保存数据到数据库

    Args:
        indicator: 指标代码
        df: DataFrame with columns: [date, value]

    Returns:
        写入的记录数
    """
    if df.empty:
        return 0

    rows = []
    for _, row in df.iterrows():
        date_str = row['date'].strftime('%Y-%m-%d')
        value = float(row['value']) if pd.notna(row['value']) else None
        rows.append((date_str, indicator, value))

    if rows:
        execute_dual_many(INSERT_SQL, rows)

    return len(rows)


# ============================================================
# 主拉取函数
# ============================================================

def fetch_indicator(indicator: str) -> Tuple[bool, int, str]:
    """
    拉取单个指标数据

    Args:
        indicator: 指标代码

    Returns:
        (是否成功, 写入记录数, 错误信息)
    """
    if indicator not in FETCH_FUNCTIONS:
        return False, 0, "未知指标: {}".format(indicator)

    config = MACRO_INDICATORS.get(indicator, {})
    indicator_name = config.get('name', indicator)

    try:
        # 获取数据库中最新日期
        latest_date = get_latest_date(indicator)
        if latest_date:
            # 增量更新：从最新日期的下一天开始
            start_dt = pd.to_datetime(latest_date) + timedelta(days=1)
            start_date = start_dt.strftime('%Y%m%d')
        else:
            # 全量拉取
            start_date = MACRO_DATA_START

        # 检查是否需要拉取
        if latest_date:
            today = date.today().strftime('%Y-%m-%d')
            if latest_date >= today:
                return True, 0, "已是最新"

        # 拉取数据
        fetch_func = FETCH_FUNCTIONS[indicator]
        df = fetch_func(start_date)

        if df.empty:
            return True, 0, "无新数据"

        # 保存数据
        count = save_data(indicator, df)

        return True, count, None

    except Exception as e:
        return False, 0, str(e)


# ============================================================
# 多指标联合拉取辅助函数
# ============================================================

def fetch_csi300_valuation_indicators() -> dict:
    """
    联合拉取沪深300 PE 和股息率（一次 AKShare 调用产生两个指标）

    Returns:
        结果字典 {indicator: {'success': bool, 'count': int, 'error': str or None}}
    """
    results = {}
    pe_key = 'pe_csi300'
    div_key = 'div_yield_csi300'

    try:
        # 以 pe_csi300 的最新日期决定起始拉取时间
        latest_date = get_latest_date(pe_key)
        if latest_date:
            today = date.today().strftime('%Y-%m-%d')
            if latest_date >= today:
                results[pe_key] = {'success': True, 'count': 0, 'error': '已是最新'}
                results[div_key] = {'success': True, 'count': 0, 'error': '已是最新'}
                return results
            start_dt = pd.to_datetime(latest_date) + timedelta(days=1)
            start_date = start_dt.strftime('%Y%m%d')
        else:
            start_date = MACRO_DATA_START

        df = fetch_csi300_valuation(start_date)

        if df.empty:
            results[pe_key] = {'success': True, 'count': 0, 'error': '无新数据'}
            results[div_key] = {'success': True, 'count': 0, 'error': '无新数据'}
            return results

        # 保存 PE
        pe_df = df[['date', 'pe']].rename(columns={'pe': 'value'}).dropna(subset=['value'])
        pe_count = save_data(pe_key, pe_df)
        results[pe_key] = {'success': True, 'count': pe_count, 'error': None}

        # 保存股息率
        div_df = df[['date', 'div_yield']].rename(columns={'div_yield': 'value'}).dropna(subset=['value'])
        div_count = save_data(div_key, div_df)
        results[div_key] = {'success': True, 'count': div_count, 'error': None}

    except Exception as e:
        err = str(e)
        results[pe_key] = {'success': False, 'count': 0, 'error': err}
        results[div_key] = {'success': False, 'count': 0, 'error': err}

    return results


def fetch_bond_yield_indicators() -> dict:
    """
    联合拉取中国和美国 10Y 国债收益率（一次 AKShare 调用产生两个指标）

    Returns:
        结果字典 {indicator: {'success': bool, 'count': int, 'error': str or None}}
    """
    results = {}
    cn_key = 'cn_10y_bond'
    us_key = 'us_10y_bond'

    try:
        latest_date = get_latest_date(cn_key)
        if latest_date:
            today = date.today().strftime('%Y-%m-%d')
            if latest_date >= today:
                results[cn_key] = {'success': True, 'count': 0, 'error': '已是最新'}
                results[us_key] = {'success': True, 'count': 0, 'error': '已是最新'}
                return results
            start_dt = pd.to_datetime(latest_date) + timedelta(days=1)
            start_date = start_dt.strftime('%Y%m%d')
        else:
            start_date = MACRO_DATA_START

        df = fetch_bond_yields(start_date)

        if df.empty:
            results[cn_key] = {'success': True, 'count': 0, 'error': '无新数据'}
            results[us_key] = {'success': True, 'count': 0, 'error': '无新数据'}
            return results

        # 保存中国国债
        cn_df = df[['date', 'cn_10y']].rename(columns={'cn_10y': 'value'}).dropna(subset=['value'])
        cn_count = save_data(cn_key, cn_df)
        results[cn_key] = {'success': True, 'count': cn_count, 'error': None}

        # 保存美国国债
        us_df = df[['date', 'us_10y']].rename(columns={'us_10y': 'value'}).dropna(subset=['value'])
        us_count = save_data(us_key, us_df)
        results[us_key] = {'success': True, 'count': us_count, 'error': None}

    except Exception as e:
        err = str(e)
        results[cn_key] = {'success': False, 'count': 0, 'error': err}
        results[us_key] = {'success': False, 'count': 0, 'error': err}

    return results


def fetch_all_indicators() -> dict:
    """
    拉取所有宏观数据指标

    pe_csi300、div_yield_csi300、cn_10y_bond、us_10y_bond 由专用联合函数处理，
    不在主循环中重复调用。

    Returns:
        结果字典 {indicator: {'success': bool, 'count': int, 'error': str or None, 'name': str}}
    """
    results = {}

    # 跳过由联合函数处理的指标
    skip_set = {'pe_csi300', 'div_yield_csi300', 'cn_10y_bond', 'us_10y_bond'}

    for indicator in FETCH_FUNCTIONS.keys():
        if indicator in skip_set:
            continue
        success, count, error = fetch_indicator(indicator)
        results[indicator] = {
            'success': success,
            'count': count,
            'error': error,
            'name': MACRO_INDICATORS.get(indicator, {}).get('name', indicator),
        }

    # 联合拉取沪深300估值
    valuation_results = fetch_csi300_valuation_indicators()
    for key, res in valuation_results.items():
        res['name'] = MACRO_INDICATORS.get(key, {}).get('name', key)
        results[key] = res

    # 联合拉取国债收益率
    bond_results = fetch_bond_yield_indicators()
    for key, res in bond_results.items():
        res['name'] = MACRO_INDICATORS.get(key, {}).get('name', key)
        results[key] = res

    return results


# ============================================================
# 主函数
# ============================================================

def main():
    print("=" * 60)
    print("宏观数据采集 (AkShare -> MySQL)")
    print("=" * 60)

    if not HAS_AKSHARE:
        print("\n错误: AKShare 未安装，请运行 pip install akshare")
        return

    # 确保表存在
    print("\n检查数据库表...")
    ensure_table_exists()
    print("  macro_data 表就绪")

    # 拉取所有指标
    print("\n开始拉取宏观数据...")
    results = fetch_all_indicators()

    # 打印结果
    print("\n" + "-" * 60)
    print("拉取结果:")
    total_count = 0
    success_count = 0
    fail_count = 0

    for indicator, result in results.items():
        status = "[OK]" if result['success'] else "[FAIL]"
        name = result['name']
        count = result['count']
        error = result['error']

        if result['success']:
            success_count += 1
            total_count += count
            print("  {} {} ({}): {} 条记录".format(status, name, indicator, count))
            if error:
                print("      备注: {}".format(error))
        else:
            fail_count += 1
            print("  {} {} ({}): 失败 - {}".format(status, name, indicator, error))

    print("\n" + "=" * 60)
    print("采集完成! 成功: {}, 失败: {}, 总写入: {} 条".format(
        success_count, fail_count, total_count))

    # 打印数据库概况
    _print_summary()


def _print_summary():
    """打印数据库概况"""
    summary = execute_query("""
        SELECT
            COUNT(DISTINCT indicator) as indicator_cnt,
            COUNT(*) as row_cnt,
            MIN(date) as min_date,
            MAX(date) as max_date
        FROM macro_data
    """)

    if summary:
        row = summary[0]
        print("\n数据库 macro_data 概况:")
        print("  {} 个指标, {:,} 条记录".format(row['indicator_cnt'], row['row_cnt']))
        print("  日期范围: {} ~ {}".format(row['min_date'], row['max_date']))

    # 各指标详情
    details = execute_query("""
        SELECT
            indicator,
            COUNT(*) as cnt,
            MIN(date) as min_date,
            MAX(date) as max_date
        FROM macro_data
        GROUP BY indicator
        ORDER BY indicator
    """)

    if details:
        print("\n  各指标详情:")
        for d in details:
            name = MACRO_INDICATORS.get(d['indicator'], {}).get('name', d['indicator'])
            print("    - {}: {} 条, {} ~ {}".format(
                name, d['cnt'], d['min_date'], d['max_date']))

    print("=" * 60)


if __name__ == "__main__":
    main()
