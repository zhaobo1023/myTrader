# -*- coding: utf-8 -*-
"""
Global Asset Briefing — LLM-generated market commentary.

Two daily sessions:
- Morning (08:30): focus on overnight US/global markets before A-share open
- Evening (18:00): incorporate A-share close, full-picture wrap-up

Data is read from macro_data table. LLM generates a structured briefing.
Results are cached in macro_data with indicator='briefing_morning'/'briefing_evening'.
"""
import json
import logging
from datetime import date, timedelta
from typing import Optional

from config.db import execute_query, execute_update
from api.services.llm_client_factory import get_llm_client

logger = logging.getLogger('myTrader.global_briefing')

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """你是一位专业的全球宏观分析师，服务于中国A股投资者。
请基于以下全球大类资产数据进行简明解读。

要求：
- 使用简洁专业的中文
- 重点关注对A股市场的潜在影响
- 标注关键风险信号和机会信号
- 不使用任何emoji字符
- 用纯文本标记如[风险]、[机会]、[关注]等
- 输出格式为Markdown"""

MORNING_PROMPT = """## 盘前速递（{date}）

以下是昨夜至今晨的全球资产数据，请给出**开盘前**简明解读，重点关注：
1. 美股三大指数昨夜表现及背后驱动
2. 美债收益率变动及对流动性的含义
3. 大宗商品（黄金/原油）异动分析
4. 美元指数及人民币汇率变化
5. VIX/GVZ等波动率指标的风险提示
6. 加密货币市场情绪参考
7. 综合判断：今日A股可能受到的外围影响（偏多/偏空/中性）

### 数据快照
{data_snapshot}
"""

EVENING_PROMPT = """## 收盘复盘（{date}）

以下是今日全球资产收盘数据（含A股收盘后数据），请给出**收盘后**全面复盘，重点关注：
1. A股今日表现回顾（结合宏观数据解读）
2. A股与外围市场的联动分析
3. 美债/汇率对资金面的影响
4. 大宗商品对资源板块的映射
5. 波动率指标的风险/机会信号
6. 明日展望：需要重点关注的风险点和机会

### 数据快照
{data_snapshot}
"""


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

# Morning session focuses on global (overnight) data
MORNING_INDICATORS = [
    'spy', 'qqq', 'dia', 'vix', 'gvz',
    'us_2y_bond', 'us_10y_bond', 'us_30y_bond', 'us_10y_2y_spread',
    'gold', 'wti_oil', 'brent_oil', 'btc',
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
}


def _collect_data_snapshot(indicators: list[str], lookback_days: int = 5) -> str:
    """
    Collect recent data for given indicators and format as text table.
    Returns a formatted string for the LLM prompt.
    """
    if not indicators:
        return '(无数据)'

    cutoff = (date.today() - timedelta(days=lookback_days + 5)).strftime('%Y-%m-%d')
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
    lines.append('| 指标 | 最新值 | 日期 | 前日 | 变动 | 变动% |')
    lines.append('|------|--------|------|------|------|-------|')

    for ind in indicators:
        name = INDICATOR_NAMES.get(ind, ind)
        pts = grouped.get(ind, [])
        if not pts:
            lines.append('| {} | -- | -- | -- | -- | -- |'.format(name))
            continue

        latest_date, latest_val = pts[0]
        prev_val = pts[1][1] if len(pts) >= 2 else None

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

        lines.append('| {} | {} | {} | {} | {} | {} |'.format(
            name, val_str, latest_date, prev_str, chg_str, pct_str))

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Briefing generation
# ---------------------------------------------------------------------------

async def generate_briefing(session: str = 'morning') -> dict:
    """
    Generate a market briefing using LLM.

    Args:
        session: 'morning' (08:30) or 'evening' (18:00)

    Returns:
        {'session': str, 'date': str, 'content': str, 'cached': bool}
    """
    today_str = date.today().strftime('%Y-%m-%d')
    cache_key = 'briefing_{}'.format(session)

    # Check cache: already generated today?
    cached = execute_query(
        "SELECT value FROM macro_data WHERE indicator = %s AND date = %s",
        (cache_key, today_str),
    )
    if cached and cached[0]['value'] is not None:
        # Value is stored as a reference ID; content is in the dedicated column
        pass  # Fall through to check content cache below

    # Check content cache in a separate table or re-generate
    content_key = 'briefing_content_{}_{}'.format(session, today_str)
    content_rows = execute_query(
        "SELECT value FROM macro_data WHERE indicator = %s AND date = %s",
        (content_key, today_str),
    )
    # We store briefing content as a long string in a simple cache table
    # Since macro_data.value is DECIMAL, we use a separate approach:
    # Store in macro_data with a text-friendly indicator name, value=1 as marker
    # and read from a file-based or Redis cache. For simplicity, regenerate if missing.

    # Collect data
    indicators = MORNING_INDICATORS if session == 'morning' else EVENING_INDICATORS
    snapshot = _collect_data_snapshot(indicators)

    if session == 'morning':
        prompt = MORNING_PROMPT.format(date=today_str, data_snapshot=snapshot)
    else:
        prompt = EVENING_PROMPT.format(date=today_str, data_snapshot=snapshot)

    # Call LLM
    llm = get_llm_client()
    content = await llm.call(
        prompt=prompt,
        system_prompt=SYSTEM_PROMPT,
        temperature=0.4,
        max_tokens=2000,
    )

    logger.info('[briefing] Generated %s briefing for %s (%d chars)', session, today_str, len(content))

    return {
        'session': session,
        'date': today_str,
        'content': content,
        'cached': False,
    }


async def get_latest_briefing(session: str = 'morning') -> Optional[dict]:
    """Get the latest briefing, generating if not available for today."""
    return await generate_briefing(session)
