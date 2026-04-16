# -*- coding: utf-8 -*-
"""
Global Asset Briefing v2 -- layered LLM-generated market commentary.

Two daily sessions:
- Morning (08:30): focus on overnight US/global markets before A-share open
- Evening (18:00): incorporate A-share close, full-picture wrap-up

Data sources:
1. macro_data table (global assets, bonds, FX, commodities)
2. A-share dashboard signals (temperature/trend/sentiment/style/stock-bond/macro)
3. ETF log bias (industry proxy via 12 tracked ETFs)
4. Limit-up/down stock details (trade_limit_stock_detail)
5. Fear & greed index (trade_fear_index)

Results cached in trade_briefing table.
"""
import json
import logging
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from config.db import execute_query, execute_update
from api.services.llm_client_factory import get_llm_client

logger = logging.getLogger('myTrader.global_briefing')

# ---------------------------------------------------------------------------
# Prompt templates (v2 -- layered structure)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """你是一位专业的A股投资顾问，为个人投资者提供每日市场研判。

## 输出格式（强制5层结构，每层必须使用对应的Markdown标题）

### 一句话研判
一句话给出市场立场。格式: **偏多/偏空/中性（高/中/低置信）| 建议仓位 X 成**

### 核心数据速览
用要点列表列出3-5个最关键的数据变动（带具体数字），不要重复原始数据表。

### 行业冷热
基于ETF偏离度数据，指出哪些板块过热需警惕、哪些突破可关注、哪些滞涨需回避。
用2-3句话概括，不要逐个ETF复述。

### 异动与事件
基于涨跌停明细和重大新闻，提炼2-3条最值得关注的个股或事件线索。
标注连板王、行业聚集效应等。无明细数据时标注"[数据不足]"。

### 风险提示
列出1-2条当前最大风险，给出明确的仓位和风格建议。

## 规则（强制，不得违反）
1. 对标记为 [MISSING] 或 [STALE] 的指标，声明"数据不可用"或"数据滞后"，绝不可编造数值
2. 绝不可编造具体数字（成交量、涨跌家数、指数涨跌幅、资金流向）——如果数据中没有提供，就不要写
3. 如果某个维度的所有核心指标均缺失，该维度输出"[数据不足]"
4. 不使用任何emoji字符，用纯文本标记如[风险]、[机会]、[关注]
5. AH股溢价指数是点位值（越高表示A股相对H股溢价越大），正常范围约10-15
6. 全文控制在600字以内，宁简勿繁
7. 如提供了"市场参考线索"，可酌情融入对应层级（行业催化->行业冷热，风险->风险提示），但不可喧宾夺主，每条线索最多用半句话带过，标注来源"""

MORNING_PROMPT = """## 盘前速递（{date}）

### 数据区1: A股大盘信号（前一交易日）
{dashboard_snapshot}

### 数据区2: 全球资产（隔夜）
{data_snapshot}

### 数据区3: ETF行业偏离度
{etf_log_bias_snapshot}

### 数据区4: 涨跌停明细（前一交易日）
{limit_stock_snapshot}

### 数据区5: 恐贪指数
{fear_greed_snapshot}
{article_hints}
请按5层结构输出盘前解读。"""

EVENING_PROMPT = """## 收盘复盘（{date}）

### 数据区1: A股大盘信号（今日）
{dashboard_snapshot}

### 数据区2: 全球资产
{data_snapshot}

### 数据区3: ETF行业偏离度
{etf_log_bias_snapshot}

### 数据区4: 涨跌停明细（今日）
{limit_stock_snapshot}

### 数据区5: 恐贪指数
{fear_greed_snapshot}
{article_hints}
请按5层结构输出收盘复盘。"""


# ---------------------------------------------------------------------------
# Data collection — macro indicators
# ---------------------------------------------------------------------------

# Morning session focuses on global (overnight) data
MORNING_INDICATORS = [
    'spy', 'qqq', 'dia', 'vix', 'gvz',
    'us_2y_bond', 'us_10y_bond', 'us_30y_bond', 'us_10y_2y_spread',
    'gold', 'wti_oil', 'btc',
    'dxy', 'usdcny',
]

# Evening session adds A-share data
EVENING_INDICATORS = MORNING_INDICATORS + [
    'idx_csi300', 'idx_csi500', 'idx_csi1000', 'idx_all_a',
    'idx_dividend', 'north_flow', 'qvix',
    'cn_10y_bond', 'pe_csi300',
]

INDICATOR_NAMES = {
    'spy': 'S&P 500 (SPY)', 'qqq': 'Nasdaq (QQQ)', 'dia': 'Dow Jones (DIA)',
    'vix': 'VIX', 'gvz': 'GVZ(黄金波动率)',
    'us_2y_bond': '美债2Y(%)', 'us_10y_bond': '美债10Y(%)',
    'us_30y_bond': '美债30Y(%)', 'us_10y_2y_spread': '10Y-2Y利差(%)',
    'gold': '黄金(USD)', 'wti_oil': 'WTI原油(USD)', 'brent_oil': '布伦特原油(USD)',
    'btc': '比特币(USD)', 'dxy': '美元指数', 'usdcny': 'USD/CNY',
    'idx_csi300': '沪深300', 'idx_csi500': '中证500', 'idx_csi1000': '中证1000',
    'idx_all_a': '中证全A', 'idx_dividend': '中证红利',
    'north_flow': '北向资金(亿)', 'qvix': 'QVIX(中国波指)',
    'cn_10y_bond': '中国10Y国债(%)', 'pe_csi300': '沪深300 PE',
    'ah_premium': 'AH股溢价指数(点位, 越高表示A股相对H股溢价越大)',
}


def _calc_staleness_tag(latest_date_str: str, target_date: date) -> str:
    """Return a freshness tag based on how stale the data is."""
    try:
        from datetime import datetime as _dt
        latest_dt = _dt.strptime(latest_date_str, '%Y-%m-%d').date()
        gap = (target_date - latest_dt).days
        if gap <= 1:
            return '[OK]'
        elif gap <= 3:
            return '[WARN: data as of {}]'.format(latest_date_str)
        else:
            return '[STALE: data as of {}, {} days old]'.format(latest_date_str, gap)
    except Exception:
        return '[MISSING]'


def _collect_data_snapshot(
    indicators: list[str],
    lookback_days: int = 5,
    target_date: date = None,
) -> tuple:
    """
    Collect recent data for given indicators and format as text table.

    Returns:
        (snapshot_text, freshness_stats) where freshness_stats =
        {'total': int, 'ok': int, 'warn': int, 'stale': int, 'missing': int}
    """
    if target_date is None:
        target_date = date.today()

    freshness_stats = {'total': len(indicators), 'ok': 0, 'warn': 0, 'stale': 0, 'missing': 0}

    if not indicators:
        return '(无数据)', freshness_stats

    cutoff = (target_date - timedelta(days=lookback_days + 5)).strftime('%Y-%m-%d')
    placeholders = ','.join(['%s'] * len(indicators))

    sql = f"""
        SELECT indicator, date, value
        FROM macro_data
        WHERE indicator IN ({placeholders}) AND date >= %s
        ORDER BY indicator, date DESC
    """
    rows = list(execute_query(sql, tuple(indicators) + (cutoff,)))

    # Group: indicator -> list of (date, value) sorted desc
    grouped: dict = {}
    for r in rows:
        key = r['indicator']
        if key not in grouped:
            grouped[key] = []
        if len(grouped[key]) < lookback_days:
            grouped[key].append((
                r['date'].strftime('%Y-%m-%d') if hasattr(r['date'], 'strftime') else str(r['date']),
                float(r['value']) if r['value'] is not None else None,
            ))

    lines = []
    lines.append('| 指标 | 最新值 | 日期 | 前日 | 变动 | 变动% | status |')
    lines.append('|------|--------|------|------|------|-------|--------|')

    for ind in indicators:
        name = INDICATOR_NAMES.get(ind, ind)
        pts = grouped.get(ind, [])
        if not pts:
            lines.append('| {} | -- | -- | -- | -- | -- | [MISSING] |'.format(name))
            freshness_stats['missing'] += 1
            continue

        latest_date, latest_val = pts[0]
        prev_val = pts[1][1] if len(pts) >= 2 else None

        # Compute staleness tag
        tag = _calc_staleness_tag(latest_date, target_date)
        if tag == '[OK]':
            freshness_stats['ok'] += 1
        elif tag == '[MISSING]':
            freshness_stats['missing'] += 1
        elif '[STALE' in tag:
            freshness_stats['stale'] += 1
        else:
            # WARN (gap <= 3d, acceptable for weekends/holidays)
            freshness_stats['warn'] += 1

        val_str = '{:.4g}'.format(latest_val) if latest_val is not None else '--'
        prev_str = '{:.4g}'.format(prev_val) if prev_val is not None else '--'

        if latest_val is not None and prev_val is not None and prev_val != 0:
            change = latest_val - prev_val
            change_pct = change / abs(prev_val) * 100
            chg_str = '{:+.4g}'.format(change)
            pct_str = '{:+.2f}%'.format(change_pct)
        else:
            chg_str = '--'
            pct_str = '--'

        lines.append('| {} | {} | {} | {} | {} | {} | {} |'.format(
            name, val_str, latest_date, prev_str, chg_str, pct_str, tag))

    return '\n'.join(lines), freshness_stats


def _collect_dashboard_snapshot() -> str:
    """
    Collect A-share dashboard signal data from the market-overview API.
    Returns formatted text for LLM prompt.
    """
    try:
        from data_analyst.market_dashboard.calculator import compute_dashboard
        data = compute_dashboard()
    except Exception as e:
        logger.warning('Failed to get dashboard data: %s', e)
        return '(大盘信号数据不可用)'

    if not data:
        return '(大盘信号数据不可用)'

    lines = []

    # Check overall freshness
    if not data.get('is_fresh', True):
        data_date = data.get('data_date', '?')
        target_date = data.get('target_date', '?')
        lines.append('[WARN: A-share data is from {}, target is {}]'.format(
            data_date, target_date))

    # Mark unavailable sections
    section_names = {
        'temperature': '市场温度',
        'trend': '趋势方向',
        'sentiment': '情绪',
        'style': '风格轮动',
        'stock_bond': '股债性价比',
        'macro': '宏观背景',
    }
    for key, label in section_names.items():
        section = data.get(key, {})
        if not section.get('available', False):
            lines.append('[MISSING: {} 数据不可用]'.format(label))

    # Temperature
    temp = data.get('temperature', {})
    if temp.get('available'):
        inds = temp.get('indicators', {})
        vol = inds.get('volume', {})
        vr = inds.get('volume_ratio_ma20', {})
        tp = inds.get('turnover_pct_rank', {})
        ad = inds.get('advance_decline', {})
        lu = inds.get('limit_up_down', {})
        lines.append('**市场温度** (信号: {})'.format(temp.get('level', '-')))
        lines.append('  成交额: {}亿 | 量/MA20: {} ({}) | 换手分位: {}%'.format(
            vol.get('value', '-'), vr.get('value', '-'), vr.get('signal', '-'), tp.get('value', '-')))
        lines.append('  涨/跌家数: {}/{} | 涨停/跌停: {}/{}'.format(
            ad.get('advance', '-'), ad.get('decline', '-'),
            lu.get('up', '-'), lu.get('down', '-')))

    # Trend
    trend = data.get('trend', {})
    if trend.get('available'):
        inds = trend.get('indicators', {})
        lines.append('**趋势方向** (信号: {})'.format(trend.get('level', '-')))
        lines.append('  均线形态: {} | ADX: {} ({}) | MACD周线: {}'.format(
            inds.get('ma_alignment', '-'),
            inds.get('adx', {}).get('value', '-'), inds.get('adx', {}).get('signal', '-'),
            inds.get('macd_weekly', {}).get('signal', '-')))

    # Sentiment
    sent = data.get('sentiment', {})
    if sent.get('available'):
        inds = sent.get('indicators', {})
        lines.append('**情绪** (综合: {} {})'.format(sent.get('score', '-'), sent.get('level_label', '-')))
        lines.append('  QVIX: {} ({}) | 北向资金: {} | 封板率: {}%'.format(
            inds.get('qvix', {}).get('value', '-'), inds.get('qvix', {}).get('signal', '-'),
            inds.get('north_flow', {}).get('signal', '-'),
            inds.get('seal_rate', {}).get('value', '-')))

    # Style
    style = data.get('style', {})
    if style.get('available'):
        scale = style.get('scale', {})
        st = style.get('style', {})
        lines.append('**风格轮动**')
        lines.append('  规模: {} (大盘{} vs 小盘{}) | 风格: {} (成长{} vs 价值{})'.format(
            scale.get('leader', '-'), scale.get('large_cap', '-'), scale.get('small_cap', '-'),
            st.get('leader', '-'), st.get('growth', '-'), st.get('value', '-')))

    # Stock-Bond
    sb = data.get('stock_bond', {})
    if sb.get('available'):
        lines.append('**股债性价比** ({})'.format(sb.get('level_label', '-')))
        spread = sb.get('spread', {})
        lines.append('  股债利差: {}% (分位: {}%)'.format(
            spread.get('value', '-'), spread.get('percentile', '-')))

    # Macro
    macro = data.get('macro', {})
    if macro.get('available'):
        inds = macro.get('indicators', {})
        lines.append('**宏观背景** ({})'.format(macro.get('level_label', '-')))
        lines.append('  PMI: {} ({}) | M2: {}% | AH股溢价指数: {} ({})'.format(
            inds.get('pmi_mfg', {}).get('value', '-'), inds.get('pmi_mfg', {}).get('signal', '-'),
            inds.get('m2_yoy', {}).get('value', '-'),
            inds.get('ah_premium', {}).get('value', '-'), inds.get('ah_premium', {}).get('signal', '-')))

    return '\n'.join(lines) if lines else '(大盘信号数据不可用)'


# ---------------------------------------------------------------------------
# Data collection — ETF log bias (industry proxy)
# ---------------------------------------------------------------------------

ETF_GROUPS = {
    '科技成长': ['159995.SZ', '515050.SH', '516160.SH', '515790.SH', '159941.SZ'],
    '消费医药': ['512690.SH', '512010.SH'],
    '周期金融': ['512880.SH', '515220.SH', '518880.SH'],
    '宽基指数': ['510300.SH', '588000.SH'],
}

STATE_CN = {
    'overheat': '过热', 'breakout': '突破', 'normal': '正常',
    'stall': '滞涨', 'pullback': '回调', 'cooldown': '冷却',
}


def _collect_etf_log_bias_snapshot() -> str:
    """Collect latest ETF log bias data grouped by sector."""
    try:
        from api.services.log_bias_service import get_latest
        data = get_latest()
    except Exception as e:
        logger.warning('Failed to get ETF log bias: %s', e)
        return '(ETF偏离度数据不可用)'

    if not data:
        return '(ETF偏离度数据不可用)'

    # Build lookup
    lookup = {d['ts_code']: d for d in data}
    trade_date = data[0].get('trade_date', '?') if data else '?'

    lines = ['数据日期: {}'.format(trade_date)]
    lines.append('| 分组 | ETF | 偏离度(%) | 状态 |')
    lines.append('|------|-----|-----------|------|')

    for group_name, codes in ETF_GROUPS.items():
        for code in codes:
            d = lookup.get(code)
            if not d:
                continue
            bias = d.get('log_bias')
            bias_str = '{:+.1f}'.format(bias) if bias is not None else '--'
            state = STATE_CN.get(d.get('signal_state', 'normal'), d.get('signal_state', '-'))
            lines.append('| {} | {} | {} | {} |'.format(
                group_name, d.get('name', code), bias_str, state))

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Data collection — limit-up/down stock details
# ---------------------------------------------------------------------------

def _collect_limit_stock_snapshot(trade_date: str = None) -> str:
    """Collect limit-up/down stock details grouped by industry."""
    if trade_date is None:
        # Use the latest available date from the detail table
        rows = execute_query(
            "SELECT MAX(trade_date) AS d FROM trade_limit_stock_detail",
            env='online',
        )
        if rows and rows[0]['d']:
            trade_date = str(rows[0]['d'])
        else:
            return '(涨跌停明细数据不可用)'

    result_lines = ['数据日期: {}'.format(trade_date)]

    for direction, label in [('up', '涨停'), ('down', '跌停')]:
        rows = execute_query(
            """SELECT stock_code, stock_name, industry, change_pct,
                      consecutive, first_limit_time
               FROM trade_limit_stock_detail
               WHERE trade_date = %s AND direction = %s
               ORDER BY consecutive DESC, amount DESC""",
            (trade_date, direction),
            env='online',
        )
        if not rows:
            result_lines.append('{}: 无数据'.format(label))
            continue

        total = len(rows)
        # Find leader (highest consecutive)
        leader = rows[0]
        leader_text = ''
        if leader.get('consecutive', 1) >= 2:
            leader_text = ' | 连板王: {}({}板)'.format(
                leader['stock_name'], leader['consecutive'])

        # Group by industry
        by_industry = defaultdict(list)
        for r in rows:
            ind = r.get('industry') or '其他'
            by_industry[ind].append(r['stock_name'])

        # Top industries by count
        sorted_inds = sorted(by_industry.items(), key=lambda x: -len(x[1]))
        industry_parts = []
        for ind_name, stocks in sorted_inds[:6]:
            stock_names = ', '.join(stocks[:3])
            if len(stocks) > 3:
                stock_names += '等{}只'.format(len(stocks))
            industry_parts.append('{}: {}'.format(ind_name, stock_names))

        result_lines.append('{} {} 只{} | {}'.format(
            label, total, leader_text, ' | '.join(industry_parts)))

    return '\n'.join(result_lines)


# ---------------------------------------------------------------------------
# Data collection — fear & greed index
# ---------------------------------------------------------------------------

def _collect_fear_greed_snapshot() -> str:
    """Collect latest fear & greed index data."""
    try:
        rows = execute_query(
            """SELECT trade_date, fear_greed_score, market_regime,
                      vix, vix_level, risk_alert
               FROM trade_fear_index
               ORDER BY trade_date DESC LIMIT 1""",
            env='online',
        )
    except Exception as e:
        logger.warning('Failed to get fear/greed index: %s', e)
        return '(恐贪指数数据不可用)'

    if not rows:
        return '(恐贪指数数据不可用)'

    r = rows[0]
    regime_cn = {
        'extreme_fear': '极度恐慌', 'fear': '恐慌', 'neutral': '中性',
        'greed': '贪婪', 'extreme_greed': '极度贪婪',
    }
    score = r.get('fear_greed_score', '-')
    regime = regime_cn.get(r.get('market_regime', ''), r.get('market_regime', '-'))
    vix = r.get('vix', '-')
    vix_level = r.get('vix_level', '-')
    risk = r.get('risk_alert') or '无'
    td = str(r['trade_date']) if r.get('trade_date') else '?'

    return '日期: {} | 恐贪指数: {}/100 ({}) | VIX: {} ({}) | 风险提示: {}'.format(
        td, score, regime, vix, vix_level, risk)


# ---------------------------------------------------------------------------
# Data collection — external article hints (optional enrichment)
# ---------------------------------------------------------------------------

def _collect_article_hints(session: str = 'morning') -> str:
    """
    Collect one-liner hints from recently digested articles.

    Returns a compact block for injection into the prompt, or empty string
    if no relevant articles exist. Designed to enrich existing layers
    without adding a new section.
    """
    try:
        from api.services.article_digest_service import get_relevant_digests
        digests = get_relevant_digests(session=session, lookback_days=1)
    except Exception as e:
        logger.debug('No article digests available: %s', e)
        return ''

    if not digests:
        return ''

    # Build compact hint lines: only one_liner + top key_view per article
    hints = []
    for d in digests[:4]:  # max 4 articles
        source = d.get('source', '')
        liner = d.get('one_liner', '')
        if not liner:
            continue
        prefix = '[{}]'.format(source) if source else ''
        hints.append('{} {}'.format(prefix, liner).strip())

    if not hints:
        return ''

    return '\n\n### 市场参考线索（外部文章提炼，仅供辅助，不可主导判断）\n' + '\n'.join(
        '- {}'.format(h) for h in hints)


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _load_briefing(session: str, brief_date: str) -> Optional[dict]:
    """Load cached briefing from DB for the given session + date."""
    rows = execute_query(
        "SELECT content, structured_data FROM trade_briefing WHERE session = %s AND brief_date = %s",
        (session, brief_date),
    )
    if rows:
        structured = None
        raw = rows[0].get('structured_data')
        if raw:
            try:
                structured = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                pass
        return {'content': rows[0]['content'], 'structured_data': structured}
    return None


def _load_latest_briefing(session: str) -> Optional[dict]:
    """Load the most recent briefing for the given session (any date)."""
    rows = execute_query(
        "SELECT content, brief_date FROM trade_briefing WHERE session = %s ORDER BY brief_date DESC LIMIT 1",
        (session,),
    )
    if rows:
        return {'content': rows[0]['content'], 'date': str(rows[0]['brief_date'])}
    return None


def _save_briefing(session: str, brief_date: str, content: str,
                   structured_data: dict = None) -> None:
    """Persist generated briefing to DB (upsert by session + date)."""
    sd_json = json.dumps(structured_data, ensure_ascii=False) if structured_data else None
    execute_update(
        """INSERT INTO trade_briefing (session, brief_date, content, structured_data)
           VALUES (%s, %s, %s, %s)
           ON DUPLICATE KEY UPDATE content = VALUES(content),
                                    structured_data = VALUES(structured_data),
                                    created_at = NOW()""",
        (session, brief_date, content, sd_json),
    )
    logger.info('[briefing] Saved %s briefing for %s to DB', session, brief_date)


# ---------------------------------------------------------------------------
# Briefing generation
# ---------------------------------------------------------------------------

def _check_overall_freshness(freshness_stats: dict) -> tuple:
    """
    Check if data quality is sufficient to generate a briefing.

    Returns:
        (ok: bool, message: str)
    """
    total = freshness_stats.get('total', 0)
    if total == 0:
        return False, '数据源未配置'

    # Only count truly stale (gap>3d) and missing as "bad"; WARN (gap<=3d, e.g. weekends) is acceptable
    bad = freshness_stats.get('missing', 0) + freshness_stats.get('stale', 0)
    if bad > total * 0.3:
        return False, (
            '数据不足：{}/{} 个指标严重过期或缺失'
            '（正常={}, 偏旧={}, 过期={}, 缺失={}）'.format(
                bad, total,
                freshness_stats.get('ok', 0),
                freshness_stats.get('warn', 0),
                freshness_stats.get('stale', 0),
                freshness_stats.get('missing', 0),
            )
        )
    return True, 'ok'


async def generate_briefing(session: str = 'morning') -> dict:
    """
    Generate a market briefing using LLM and persist to DB.

    Args:
        session: 'morning' (08:30) or 'evening' (18:00)

    Returns:
        {'session': str, 'date': str, 'content': str, 'cached': bool,
         'data_quality': dict, 'structured_data': dict}
    """
    today_str = date.today().strftime('%Y-%m-%d')

    # --- 1. Collect macro data ---
    indicators = MORNING_INDICATORS if session == 'morning' else EVENING_INDICATORS
    snapshot, freshness_stats = _collect_data_snapshot(indicators)

    # --- 2. Collect A-share dashboard ---
    dashboard_snapshot = _collect_dashboard_snapshot()

    # --- 3. Collect ETF log bias ---
    etf_log_bias_snapshot = _collect_etf_log_bias_snapshot()

    # --- 4. Collect limit-up/down details ---
    limit_stock_snapshot = _collect_limit_stock_snapshot()

    # --- 5. Collect fear & greed ---
    fear_greed_snapshot = _collect_fear_greed_snapshot()

    # --- 6. Collect article hints (optional, non-blocking) ---
    article_hints = _collect_article_hints(session)

    # Build data_quality info
    quality_ok, quality_msg = _check_overall_freshness(freshness_stats)
    data_quality = {
        **freshness_stats,
        'sufficient': quality_ok,
        'message': quality_msg,
    }

    # Build structured_data for persistence
    structured_data = {
        'version': 2,
        'freshness': freshness_stats,
        'etf_log_bias_text': etf_log_bias_snapshot,
        'limit_stock_text': limit_stock_snapshot,
        'fear_greed_text': fear_greed_snapshot,
    }

    # Abort if data quality is too poor
    if not quality_ok:
        logger.warning('[briefing] Aborting %s briefing: %s', session, quality_msg)
        return {
            'session': session,
            'date': today_str,
            'content': '[速递中止] {}'.format(quality_msg),
            'cached': False,
            'data_quality': data_quality,
        }

    template = MORNING_PROMPT if session == 'morning' else EVENING_PROMPT
    prompt = template.format(
        date=today_str,
        data_snapshot=snapshot,
        dashboard_snapshot=dashboard_snapshot,
        etf_log_bias_snapshot=etf_log_bias_snapshot,
        limit_stock_snapshot=limit_stock_snapshot,
        fear_greed_snapshot=fear_greed_snapshot,
        article_hints=article_hints,
    )

    # Call LLM
    llm = get_llm_client()
    content = await llm.call(
        prompt=prompt,
        system_prompt=SYSTEM_PROMPT,
        temperature=0.4,
        max_tokens=2500,
    )

    logger.info('[briefing] Generated %s briefing for %s (%d chars)', session, today_str, len(content))

    # Persist to DB
    try:
        _save_briefing(session, today_str, content, structured_data=structured_data)
    except Exception as e:
        logger.warning('[briefing] Failed to save to DB: %s', e)

    return {
        'session': session,
        'date': today_str,
        'content': content,
        'cached': False,
        'data_quality': data_quality,
        'structured_data': structured_data,
    }


async def get_latest_briefing(session: str = 'morning', force: bool = False) -> Optional[dict]:
    """Get the latest briefing. Returns cached version if available, generates otherwise.

    Time-awareness:
      - morning session is valid after 08:30
      - evening session is valid after 18:00
      If current time is before the session window AND no today's cache exists,
      return the most recent historical briefing instead of generating a new one.
    """
    from datetime import datetime
    now = datetime.now()
    today_str = date.today().strftime('%Y-%m-%d')
    session_cutoffs = {'morning': 8, 'evening': 18}
    cutoff_hour = session_cutoffs.get(session, 8)

    # Try loading today's cache from DB unless force regenerate
    if not force:
        try:
            cached = _load_briefing(session, today_str)
            if cached:
                logger.info('[briefing] Returning cached %s briefing for %s', session, today_str)
                return {
                    'session': session,
                    'date': today_str,
                    'content': cached['content'],
                    'cached': True,
                    'structured_data': cached.get('structured_data'),
                }
        except Exception as e:
            logger.warning('[briefing] Failed to load cached briefing: %s', e)

        # Before session time and no today's cache -- return most recent historical
        if now.hour < cutoff_hour:
            try:
                latest = _load_latest_briefing(session)
                if latest:
                    logger.info('[briefing] Before %s:00, returning latest historical %s briefing from %s',
                                cutoff_hour, session, latest['date'])
                    return {
                        'session': session,
                        'date': latest['date'],
                        'content': latest['content'],
                        'cached': True,
                    }
            except Exception as e:
                logger.warning('[briefing] Failed to load latest briefing: %s', e)

    return await generate_briefing(session)
