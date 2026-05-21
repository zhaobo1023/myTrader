# -*- coding: utf-8 -*-
"""
批量股票分析报告生成器

用法:
    python scripts/batch_stock_report.py --codes 600519 000858 601318
    python scripts/batch_stock_report.py --sector 银行
    python scripts/batch_stock_report.py --codes 600519 --sector 白酒

输出: output/reports/<stock_code>_<date>.md
"""
import argparse
import logging
import os
import sys
from datetime import date, timedelta
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.db import execute_query, get_online_connection

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_DIR = os.path.join(ROOT, 'output', 'reports')
MAX_RETRIES = 3
ENV = 'online'


# ============================================================
# Connection test
# ============================================================

def test_connection() -> bool:
    """Test DB connectivity before running the batch."""
    try:
        rows = list(execute_query('SELECT COUNT(*) AS cnt FROM trade_stock_basic', env=ENV))
        count = rows[0]['cnt']
        logger.info('[OK] Connection test passed. trade_stock_basic has %d rows.', count)
        return True
    except Exception as e:
        logger.error('[FAIL] Connection test failed: %s', e)
        return False


# ============================================================
# Query helpers with retry + auto-fix
# ============================================================

def _fix_sql(sql: str, error: str) -> Optional[str]:
    """
    Simple rule-based SQL fixer for common errors.
    Returns fixed SQL or None if unfixable.
    """
    err = str(error).lower()

    # Unknown column: strip the problematic column
    if "unknown column" in err:
        import re
        m = re.search(r"unknown column '([^']+)'", err, re.IGNORECASE)
        if m:
            bad_col = m.group(1).split('.')[-1]
            # Try removing the column from SELECT
            fixed = re.sub(
                r',?\s*\b' + re.escape(bad_col) + r'\b[^,\n)]*',
                '',
                sql,
                count=1,
                flags=re.IGNORECASE,
            )
            if fixed != sql:
                logger.warning('[AUTO-FIX] Removed unknown column %s', bad_col)
                return fixed

    # Table doesn't exist: nothing we can do
    if "doesn't exist" in err or "table" in err and "exist" in err:
        return None

    # Too many connections: just retry as-is
    if "too many connections" in err or "connection" in err:
        import time
        time.sleep(2)
        return sql

    return None


def safe_query(sql: str, params=None, label: str = '') -> list:
    """Execute a query with up to MAX_RETRIES attempts and auto-fix."""
    last_err = None
    current_sql = sql
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            conn = get_online_connection()
            from pymysql.cursors import DictCursor
            cur = conn.cursor(DictCursor)
            cur.execute(current_sql, params or ())
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return list(rows)
        except Exception as e:
            last_err = e
            logger.warning('[%s] Attempt %d/%d failed: %s', label or 'query', attempt, MAX_RETRIES, e)
            if attempt < MAX_RETRIES:
                fixed = _fix_sql(current_sql, str(e))
                if fixed:
                    current_sql = fixed
                    logger.info('[%s] Retrying with fixed SQL', label or 'query')
                else:
                    import time
                    time.sleep(1)
    logger.error('[%s] All %d attempts failed. Last error: %s', label or 'query', MAX_RETRIES, last_err)
    return []


# ============================================================
# Data fetchers
# ============================================================

def fetch_basic_info(code: str) -> dict:
    rows = safe_query(
        "SELECT stock_code, stock_name, is_st, industry, sw_level1, sw_level2 "
        "FROM trade_stock_basic WHERE stock_code = %s",
        (code,), label='basic_info',
    )
    return rows[0] if rows else {}


def fetch_latest_price(code: str) -> dict:
    # Fetch price and valuation separately: daily_basic may lag behind daily
    price_rows = safe_query(
        "SELECT trade_date, close_price, open_price, high_price, "
        "low_price, volume, amount, turnover_rate "
        "FROM trade_stock_daily WHERE stock_code = %s "
        "ORDER BY trade_date DESC LIMIT 1",
        (code,), label='latest_price',
    )
    basic_rows = safe_query(
        "SELECT pe_ttm, pb, total_mv, circ_mv "
        "FROM trade_stock_daily_basic WHERE stock_code = %s "
        "ORDER BY trade_date DESC LIMIT 1",
        (code,), label='latest_basic',
    )
    result = dict(price_rows[0]) if price_rows else {}
    if basic_rows:
        result.update(basic_rows[0])
    return result


def fetch_price_history(code: str, days: int = 60) -> list:
    start = (date.today() - timedelta(days=days * 2)).strftime('%Y-%m-%d')
    rows = safe_query(
        "SELECT trade_date, close_price, volume, amount, turnover_rate "
        "FROM trade_stock_daily "
        "WHERE stock_code = %s AND trade_date >= %s "
        "ORDER BY trade_date DESC LIMIT %s",
        (code, start, days), label='price_history',
    )
    return rows


def fetch_financials(code: str) -> list:
    rows = safe_query(
        "SELECT report_date, report_type, revenue, net_profit, net_profit_yoy, "
        "roe, gross_margin, eps "
        "FROM financial_income "
        "WHERE stock_code = %s "
        "ORDER BY report_date DESC LIMIT 8",
        (code,), label='financials',
    )
    return rows


def fetch_balance(code: str) -> list:
    rows = safe_query(
        "SELECT report_date, total_assets, total_equity, loan_total, "
        "npl_ratio, cap_adequacy_ratio, nim "
        "FROM financial_balance "
        "WHERE stock_code = %s "
        "ORDER BY report_date DESC LIMIT 4",
        (code,), label='balance',
    )
    return rows


def fetch_rps(code: str) -> dict:
    rows = safe_query(
        "SELECT trade_date, rps_20, rps_60, rps_120, rps_250, rps_slope "
        "FROM trade_stock_rps "
        "WHERE stock_code = %s "
        "ORDER BY trade_date DESC LIMIT 1",
        (code,), label='rps',
    )
    return rows[0] if rows else {}


def fetch_extended_factor(code: str) -> dict:
    rows = safe_query(
        "SELECT calc_date, mom_5, mom_10, reversal_1, turnover_20_mean, "
        "roe_ttm, gross_margin, net_profit_growth, revenue_growth "
        "FROM trade_stock_extended_factor "
        "WHERE stock_code = %s "
        "ORDER BY calc_date DESC LIMIT 1",
        (code,), label='extended_factor',
    )
    return rows[0] if rows else {}


def fetch_moneyflow(code: str, days: int = 5) -> list:
    start = (date.today() - timedelta(days=days * 2)).strftime('%Y-%m-%d')
    rows = safe_query(
        "SELECT trade_date, net_mf_amount, buy_lg_amount, sell_lg_amount, "
        "buy_elg_amount, sell_elg_amount "
        "FROM trade_stock_moneyflow "
        "WHERE stock_code = %s AND trade_date >= %s "
        "ORDER BY trade_date DESC LIMIT %s",
        (code, start, days), label='moneyflow',
    )
    return rows


def fetch_concepts(code: str) -> list:
    rows = safe_query(
        "SELECT concept_name, source "
        "FROM stock_concept_map "
        "WHERE stock_code = %s "
        "ORDER BY concept_name",
        (code,), label='concepts',
    )
    return rows


def fetch_composite_score(code: str) -> dict:
    rows = safe_query(
        "SELECT score_date, score_technical, score_fund_flow, score_fundamental, "
        "score_sentiment, composite_score, direction, key_signal "
        "FROM composite_scores "
        "WHERE code = %s "
        "ORDER BY score_date DESC LIMIT 1",
        (code,), label='composite_score',
    )
    return rows[0] if rows else {}


def fetch_valuation(code: str) -> dict:
    rows = safe_query(
        "SELECT trade_date, pe_ttm, pb, ps_ttm, dividend_yield, "
        "total_mv, val_label, pe_q1yr, pe_q3yr, pe_q5yr "
        "FROM research_valuation_daily "
        "WHERE code = %s "
        "ORDER BY trade_date DESC LIMIT 1",
        (code,), label='valuation',
    )
    return rows[0] if rows else {}


def fetch_sector_peers(sw_level1: str, exclude_code: str, limit: int = 8) -> list:
    """Fetch top peers by market cap in the same SW level-1 sector.

    Uses COLLATE utf8mb4_unicode_ci on the sw_level1 comparison to avoid
    collation mismatch between trade_stock_basic (utf8mb4_0900_ai_ci) and
    trade_stock_daily_basic (utf8mb4_unicode_ci).
    """
    if not sw_level1:
        return []
    rows = safe_query(
        "SELECT b.stock_code, b.stock_name, "
        "db.total_mv, db.pe_ttm, db.pb "
        "FROM trade_stock_basic b "
        "JOIN trade_stock_daily_basic db "
        "  ON b.stock_code COLLATE utf8mb4_unicode_ci = db.stock_code "
        "WHERE b.sw_level1 COLLATE utf8mb4_unicode_ci = %s "
        "  AND b.stock_code != %s "
        "  AND db.trade_date = ("
        "    SELECT MAX(trade_date) FROM trade_stock_daily_basic "
        "    WHERE stock_code = b.stock_code COLLATE utf8mb4_unicode_ci"
        "  ) "
        "ORDER BY db.total_mv DESC LIMIT %s",
        (sw_level1, exclude_code, limit), label='sector_peers',
    )
    return rows


def resolve_sector_codes(sector_kw: str) -> list:
    """Return stock codes matching a sector keyword (SW level1/level2/industry)."""
    kw = f'%{sector_kw}%'
    rows = safe_query(
        "SELECT DISTINCT stock_code FROM trade_stock_basic "
        "WHERE sw_level1 LIKE %s OR sw_level2 LIKE %s OR industry LIKE %s",
        (kw, kw, kw), label='sector_resolve',
    )
    return [r['stock_code'] for r in rows]


# ============================================================
# Signal generation
# ============================================================

def _pct(val, digits=1):
    if val is None:
        return 'N/A'
    return f'{float(val)*100:.{digits}f}%'


def _num(val, digits=2):
    if val is None:
        return 'N/A'
    try:
        return f'{float(val):.{digits}f}'
    except (TypeError, ValueError):
        return 'N/A'


def _mv_label(mv_wan: float) -> str:
    """Convert 万元 to readable label."""
    if mv_wan is None:
        return 'N/A'
    mv = float(mv_wan)
    if mv >= 1e8:
        return f'{mv/1e8:.1f}万亿'
    if mv >= 1e4:
        return f'{mv/1e4:.0f}亿'
    return f'{mv:.0f}万'


def compute_price_signals(history: list) -> dict:
    """Compute momentum and volatility from price history."""
    if len(history) < 5:
        return {}
    closes = [float(r['close_price']) for r in history]
    latest = closes[0]
    ret_5d = (latest - closes[4]) / closes[4] * 100 if len(closes) >= 5 else None
    ret_20d = (latest - closes[19]) / closes[19] * 100 if len(closes) >= 20 else None
    ret_60d = (latest - closes[-1]) / closes[-1] * 100 if len(closes) >= 60 else None

    # 20-day volatility (annualized)
    import math
    if len(closes) >= 21:
        rets = [(closes[i] - closes[i+1]) / closes[i+1] for i in range(20)]
        mean_r = sum(rets) / len(rets)
        var = sum((r - mean_r) ** 2 for r in rets) / len(rets)
        vol_20 = math.sqrt(var * 250) * 100
    else:
        vol_20 = None

    return {
        'ret_5d': ret_5d,
        'ret_20d': ret_20d,
        'ret_60d': ret_60d,
        'vol_20d_ann': vol_20,
        'latest': latest,
    }


def generate_signals(basic, price, rps, factor, score, valuation, mf) -> list:
    """Return a list of (signal_type, description) tuples."""
    signals = []

    # Technical signals from RPS
    if rps:
        r120 = rps.get('rps_120')
        r250 = rps.get('rps_250')
        slope = rps.get('rps_slope')
        if r120 and float(r120) >= 80:
            signals.append(('[BULL]', f'RPS120={_num(r120, 1)} - 中期相对强度领先市场'))
        if r250 and float(r250) >= 80:
            signals.append(('[BULL]', f'RPS250={_num(r250, 1)} - 长期相对强度领先市场'))
        if r120 and float(r120) < 30:
            signals.append(('[BEAR]', f'RPS120={_num(r120, 1)} - 中期相对强度偏弱'))
        if slope and float(slope) > 0.3:
            signals.append(('[BULL]', f'RPS斜率={_num(slope, 2)} - 动量加速上升'))

    # Valuation signals
    if valuation:
        label = valuation.get('val_label', '')
        pe_q1 = valuation.get('pe_q1yr')
        pe_q3 = valuation.get('pe_q3yr')
        if label == 'LOW':
            signals.append(('[BULL]', '估值处于历史低位区间'))
        elif label == 'HIGH':
            signals.append(('[BEAR]', '估值处于历史高位区间'))
        if pe_q1 and float(pe_q1) < 0.25:
            signals.append(('[BULL]', f'PE百分位={_pct(pe_q1)} - 历史低估'))

    # Fundamental signals
    if factor:
        np_growth = factor.get('net_profit_growth')
        rev_growth = factor.get('revenue_growth')
        roe = factor.get('roe_ttm')
        if np_growth and float(np_growth) > 0.20:
            signals.append(('[BULL]', f'净利润增速={_pct(np_growth, 1)} - 盈利高增长'))
        if np_growth and float(np_growth) < -0.20:
            signals.append(('[BEAR]', f'净利润增速={_pct(np_growth, 1)} - 盈利明显下滑'))
        if roe and float(roe) > 15:
            # roe_ttm is stored as percentage value (e.g. 26.37 means 26.37%)
            signals.append(('[BULL]', f'ROE_TTM={_num(roe, 1)}% - 盈利质量优秀'))

    # Fund flow signals
    if mf:
        net_total = sum(float(r.get('net_mf_amount') or 0) for r in mf)
        if net_total > 0:
            signals.append(('[BULL]', f'近{len(mf)}日净流入 {net_total/1e4:.0f}万元'))
        else:
            signals.append(('[BEAR]', f'近{len(mf)}日净流出 {abs(net_total)/1e4:.0f}万元'))

    # Composite score
    if score:
        cs = score.get('composite_score')
        direction = score.get('direction', '')
        if cs and int(cs) >= 70:
            signals.append(('[BULL]', f'综合评分={cs} 方向={direction}'))
        elif cs and int(cs) <= 30:
            signals.append(('[BEAR]', f'综合评分={cs} 方向={direction}'))

    if not signals:
        signals.append(('[NEUTRAL]', '暂无明显多空信号'))
    return signals


# ============================================================
# Report builder
# ============================================================

def build_report(code: str) -> Optional[str]:
    logger.info('Analyzing %s...', code)

    # Normalize code: strip suffix for financial_income/balance queries
    bare_code = code.replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
    # Determine suffixed code for price tables
    if '.' not in code:
        # Guess suffix from code pattern
        if code.startswith(('6', '9')):
            full_code = code + '.SH'
        elif code.startswith(('0', '2', '3')):
            full_code = code + '.SZ'
        elif code.startswith('8') or code.startswith('4'):
            full_code = code + '.BJ'
        else:
            full_code = code
    else:
        full_code = code

    # Fetch all data
    basic = fetch_basic_info(full_code) or fetch_basic_info(bare_code)
    if not basic:
        logger.warning('No basic info for %s, skipping.', code)
        return None

    price = fetch_latest_price(full_code)
    history = fetch_price_history(full_code)
    financials = fetch_financials(bare_code)
    balance = fetch_balance(bare_code)
    rps = fetch_rps(full_code)
    factor = fetch_extended_factor(full_code)
    mf = fetch_moneyflow(full_code)
    concepts = fetch_concepts(bare_code) or fetch_concepts(full_code)
    score = fetch_composite_score(full_code) or fetch_composite_score(bare_code)
    valuation = fetch_valuation(bare_code) or fetch_valuation(full_code)
    peers = fetch_sector_peers(basic.get('sw_level1', ''), full_code)

    price_signals = compute_price_signals(history)
    investment_signals = generate_signals(basic, price, rps, factor, score, valuation, mf)

    # ---- Build Markdown ----
    today = date.today().strftime('%Y-%m-%d')
    name = basic.get('stock_name', '未知')
    sw1 = basic.get('sw_level1', 'N/A')
    sw2 = basic.get('sw_level2', 'N/A')
    industry = basic.get('industry', 'N/A')

    lines = []
    lines.append(f'# {name}({bare_code}) 投资分析报告')
    lines.append('')
    lines.append(f'> 生成时间: {today}  |  数据来源: myTrader online DB')
    lines.append('')

    # ---- 1. Company Overview ----
    lines.append('## 1. 公司概况')
    lines.append('')
    lines.append('| 项目 | 内容 |')
    lines.append('|------|------|')
    lines.append(f'| 股票代码 | {bare_code} |')
    lines.append(f'| 股票名称 | {name} |')
    lines.append(f'| ST状态 | {"[ST]" if basic.get("is_st") else "正常"} |')
    lines.append(f'| 申万一级 | {sw1} |')
    lines.append(f'| 申万二级 | {sw2} |')
    lines.append(f'| 行业 | {industry} |')
    lines.append('')

    # ---- 2. Recent Price Action ----
    lines.append('## 2. 近期价格走势')
    lines.append('')
    if price:
        td = price.get('trade_date', 'N/A')
        close = _num(price.get('close_price'), 2)
        mv = _mv_label(price.get('total_mv'))
        pe = _num(price.get('pe_ttm'), 1)
        pb = _num(price.get('pb'), 2)
        lines.append('| 项目 | 数值 |')
        lines.append('|------|------|')
        lines.append(f'| 最新收盘价 | {close} |')
        lines.append(f'| 最新交易日 | {td} |')
        lines.append(f'| 总市值 | {mv} |')
        lines.append(f'| PE(TTM) | {pe} |')
        lines.append(f'| PB | {pb} |')
        lines.append('')

    if price_signals:
        ret5 = price_signals.get('ret_5d')
        ret20 = price_signals.get('ret_20d')
        ret60 = price_signals.get('ret_60d')
        vol = price_signals.get('vol_20d_ann')
        lines.append('| 涨跌幅 | 数值 |')
        lines.append('|--------|------|')
        if ret5 is not None:
            lines.append(f'| 近5日 | {ret5:+.1f}% |')
        if ret20 is not None:
            lines.append(f'| 近20日 | {ret20:+.1f}% |')
        if ret60 is not None:
            lines.append(f'| 近60日 | {ret60:+.1f}% |')
        if vol is not None:
            lines.append(f'| 20日年化波动率 | {vol:.1f}% |')
        lines.append('')

    # RPS
    if rps:
        lines.append('**相对强弱(RPS)**')
        lines.append('')
        lines.append('| 周期 | RPS |')
        lines.append('|------|-----|')
        for period in [20, 60, 120, 250]:
            val = rps.get(f'rps_{period}')
            if val is not None:
                lines.append(f'| {period}日 | {_num(val, 1)} |')
        slope = rps.get('rps_slope')
        if slope:
            lines.append(f'| 斜率 | {_num(slope, 3)} |')
        lines.append('')

    # ---- 3. Sector Analysis ----
    lines.append('## 3. 行业与题材分析')
    lines.append('')
    lines.append(f'**所在行业:** {sw1} / {sw2}')
    lines.append('')

    if concepts:
        concept_names = [c['concept_name'] for c in concepts[:20]]
        lines.append(f'**相关题材:** {", ".join(concept_names)}')
        lines.append('')

    if peers:
        lines.append('**同行业龙头(按市值):**')
        lines.append('')
        lines.append('| 代码 | 名称 | 总市值 | PE(TTM) | PB |')
        lines.append('|------|------|--------|---------|-----|')
        for p in peers:
            lines.append(
                f'| {p["stock_code"]} | {p["stock_name"]} | '
                f'{_mv_label(p.get("total_mv"))} | '
                f'{_num(p.get("pe_ttm"), 1)} | '
                f'{_num(p.get("pb"), 2)} |'
            )
        lines.append('')

    # ---- 4. Key Financials ----
    lines.append('## 4. 核心财务数据')
    lines.append('')

    if financials:
        lines.append('**利润表 (近期报告期)**')
        lines.append('')
        lines.append('| 报告期 | 类型 | 营收 | 净利润 | 净利同比 | ROE | 毛利率 | EPS |')
        lines.append('|--------|------|------|--------|---------|-----|--------|-----|')
        for f in financials[:6]:
            # revenue / net_profit already in 亿元; roe/gross_margin/net_profit_yoy
            # are stored as percentage values (e.g. 24.64 means 24.64%)
            rev = float(f['revenue']) if f.get('revenue') else None
            np_ = float(f['net_profit']) if f.get('net_profit') else None
            lines.append(
                f'| {f.get("report_date", "N/A")} '
                f'| {f.get("report_type", "N/A")} '
                f'| {_num(rev, 2) + "亿" if rev is not None else "N/A"} '
                f'| {_num(np_, 2) + "亿" if np_ is not None else "N/A"} '
                f'| {_num(f.get("net_profit_yoy"), 1) + "%" if f.get("net_profit_yoy") is not None else "N/A"} '
                f'| {_num(f.get("roe"), 1) + "%" if f.get("roe") is not None else "N/A"} '
                f'| {_num(f.get("gross_margin"), 1) + "%" if f.get("gross_margin") is not None else "N/A"} '
                f'| {_num(f.get("eps"), 2)} |'
            )
        lines.append('')

    if balance:
        lines.append('**资产负债表**')
        lines.append('')
        lines.append('| 报告期 | 总资产 | 总权益 | 有息负债 | 不良率 | 资本充足率 | NIM |')
        lines.append('|--------|--------|--------|---------|--------|-----------|-----|')
        for b in balance[:4]:
            # total_assets/equity/loan_total stored in 亿元
            # npl_ratio/cap_adequacy_ratio/nim stored as percentage values
            ta = float(b['total_assets']) if b.get('total_assets') else None
            te = float(b['total_equity']) if b.get('total_equity') else None
            lt = float(b['loan_total']) if b.get('loan_total') else None
            lines.append(
                f'| {b.get("report_date", "N/A")} '
                f'| {_num(ta, 1) + "亿" if ta is not None else "N/A"} '
                f'| {_num(te, 1) + "亿" if te is not None else "N/A"} '
                f'| {_num(lt, 1) + "亿" if lt is not None else "N/A"} '
                f'| {_num(b.get("npl_ratio"), 2) + "%" if b.get("npl_ratio") is not None else "N/A"} '
                f'| {_num(b.get("cap_adequacy_ratio"), 2) + "%" if b.get("cap_adequacy_ratio") is not None else "N/A"} '
                f'| {_num(b.get("nim"), 2) + "%" if b.get("nim") is not None else "N/A"} |'
            )
        lines.append('')

    if factor:
        lines.append('**增长因子 (最新)**')
        lines.append('')
        lines.append('| 指标 | 数值 |')
        lines.append('|------|------|')
        np_g = factor.get('net_profit_growth')
        rev_g = factor.get('revenue_growth')
        roe_ttm = factor.get('roe_ttm')
        gm = factor.get('gross_margin')
        t20 = factor.get('turnover_20_mean')
        if np_g is not None:
            # net_profit_growth / revenue_growth stored as decimal (0.06 = 6%)
            lines.append(f'| 净利润增速 | {_pct(np_g, 1)} |')
        if rev_g is not None:
            lines.append(f'| 营收增速 | {_pct(rev_g, 1)} |')
        if roe_ttm is not None:
            # roe_ttm / gross_margin stored as percentage value (26.37 = 26.37%)
            lines.append(f'| ROE_TTM | {_num(roe_ttm, 1)}% |')
        if gm is not None:
            lines.append(f'| 毛利率 | {_num(gm, 1)}% |')
        if t20 is not None:
            lines.append(f'| 20日平均换手率 | {_num(t20, 2)}% |')
        lines.append('')

    # Valuation percentile
    if valuation:
        lines.append('**估值百分位**')
        lines.append('')
        lines.append('| 指标 | 当前值 | 1年分位 | 3年分位 | 5年分位 | 标签 |')
        lines.append('|------|--------|---------|---------|---------|------|')
        lines.append(
            f'| PE(TTM) | {_num(valuation.get("pe_ttm"), 1)} '
            f'| {_pct(valuation.get("pe_q1yr"), 1)} '
            f'| {_pct(valuation.get("pe_q3yr"), 1)} '
            f'| {_pct(valuation.get("pe_q5yr"), 1)} '
            f'| {valuation.get("val_label", "N/A")} |'
        )
        lines.append('')

    # ---- 5. Fund Flow ----
    if mf:
        lines.append('## 5. 资金流向')
        lines.append('')
        lines.append('| 日期 | 净流入(万) | 大单净流入(万) | 超大单净流入(万) |')
        lines.append('|------|-----------|--------------|----------------|')
        for m in mf:
            net = float(m.get('net_mf_amount') or 0) / 1e4
            lg_b = float(m.get('buy_lg_amount') or 0) / 1e4
            lg_s = float(m.get('sell_lg_amount') or 0) / 1e4
            elg_b = float(m.get('buy_elg_amount') or 0) / 1e4
            elg_s = float(m.get('sell_elg_amount') or 0) / 1e4
            lg_net = lg_b - lg_s
            elg_net = elg_b - elg_s
            lines.append(
                f'| {m.get("trade_date", "N/A")} '
                f'| {net:+.0f} '
                f'| {lg_net:+.0f} '
                f'| {elg_net:+.0f} |'
            )
        lines.append('')

    # ---- 6. Composite Score ----
    if score:
        lines.append('## 6. 综合评分')
        lines.append('')
        lines.append('| 维度 | 评分 |')
        lines.append('|------|------|')
        lines.append(f'| 技术面 | {score.get("score_technical", "N/A")} |')
        lines.append(f'| 资金流 | {score.get("score_fund_flow", "N/A")} |')
        lines.append(f'| 基本面 | {score.get("score_fundamental", "N/A")} |')
        lines.append(f'| 情绪面 | {score.get("score_sentiment", "N/A")} |')
        lines.append(f'| 综合分 | **{score.get("composite_score", "N/A")}** |')
        lines.append(f'| 方向判断 | {score.get("direction", "N/A")} |')
        key_signal = score.get('key_signal', '')
        if key_signal:
            lines.append('')
            lines.append(f'**关键信号:** {key_signal}')
        lines.append('')

    # ---- 7. Investment Signals ----
    lines.append('## 7. 投资信号汇总')
    lines.append('')
    for sig_type, desc in investment_signals:
        lines.append(f'- **{sig_type}** {desc}')
    lines.append('')

    lines.append('---')
    lines.append('*本报告由 myTrader 批量分析管道自动生成，仅供参考，不构成投资建议。*')

    return '\n'.join(lines)


# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='批量股票分析报告生成器')
    parser.add_argument('--codes', nargs='+', default=[], help='股票代码列表，如 600519 000858')
    parser.add_argument('--sector', nargs='+', default=[], help='行业关键词，如 银行 白酒')
    args = parser.parse_args()

    # 1. Connection test
    if not test_connection():
        sys.exit(1)

    # 2. Resolve codes
    all_codes = list(args.codes)
    for kw in args.sector:
        resolved = resolve_sector_codes(kw)
        if resolved:
            logger.info('Sector "%s" resolved to %d stocks', kw, len(resolved))
            all_codes.extend(resolved)
        else:
            logger.warning('No stocks found for sector keyword: %s', kw)

    if not all_codes:
        logger.error('No stock codes to process. Use --codes or --sector.')
        sys.exit(1)

    # Deduplicate preserving order
    seen = set()
    unique_codes = []
    for c in all_codes:
        if c not in seen:
            seen.add(c)
            unique_codes.append(c)

    logger.info('Processing %d stocks: %s', len(unique_codes), ', '.join(unique_codes[:10]))

    os.makedirs(REPORT_DIR, exist_ok=True)
    today = date.today().strftime('%Y%m%d')

    success, failed = 0, []
    for code in unique_codes:
        try:
            md = build_report(code)
            if md is None:
                failed.append(code)
                continue
            bare = code.replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
            path = os.path.join(REPORT_DIR, f'{bare}_{today}.md')
            with open(path, 'w', encoding='utf-8') as f:
                f.write(md)
            logger.info('[OK] %s -> %s', code, os.path.relpath(path))
            success += 1
        except Exception as e:
            logger.error('[FAIL] %s: %s', code, e)
            failed.append(code)

    logger.info('Done. Success=%d, Failed=%d', success, len(failed))
    if failed:
        logger.warning('Failed codes: %s', ', '.join(failed))


if __name__ == '__main__':
    main()
