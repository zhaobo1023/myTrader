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

SYSTEM_PROMPT = """你是一位专业的A股市场分析师。
请基于以下A股大盘信号和全球资产数据进行简明解读。

要求：
- 使用简洁专业的中文，重点服务A股投资者
- A股大盘信号（市场温度/趋势/情绪/风格/股债/宏观）是核心，全球资产是辅助参考
- 标注关键风险信号和机会信号
- 不使用任何emoji字符
- 用纯文本标记如[风险]、[机会]、[关注]等
- 输出格式为Markdown，控制在800字以内"""

MORNING_PROMPT = """## 盘前速递（{date}）

以下是A股大盘信号和昨夜全球资产数据，请给出**开盘前**简明解读：

### 一、A股大盘信号（前一交易日）
{dashboard_snapshot}

### 二、全球资产（隔夜）
{data_snapshot}

请从以下维度解读：
1. **A股市场状态**：基于温度/趋势/情绪信号，判断当前所处阶段
2. **外围影响**：美股/美债/商品对A股今日可能的映射
3. **风格与资金**：大小盘/成长价值偏好、北向资金方向
4. **风险提示**：当前最需警惕的风险因素
5. **操作建议**：今日整体偏多/偏空/中性，仓位建议
"""

EVENING_PROMPT = """## 收盘复盘（{date}）

以下是今日A股大盘信号和全球资产数据，请给出**收盘后**全面复盘：

### 一、A股大盘信号（今日）
{dashboard_snapshot}

### 二、全球资产
{data_snapshot}

请从以下维度解读：
1. **今日行情回顾**：结合温度/趋势/情绪信号，概括今日市场特征
2. **资金面分析**：北向资金、融资余额、成交量变化的含义
3. **风格轮动**：大小盘/成长价值表现，轮动方向判断
4. **股债性价比**：当前股债利差水平的配置含义
5. **外围联动**：全球资产对明日A股的潜在影响
6. **明日展望**：需关注的风险点和机会，仓位建议
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
        lines.append('  PMI: {} ({}) | M2: {}% | AH溢价: {} ({})'.format(
            inds.get('pmi_mfg', {}).get('value', '-'), inds.get('pmi_mfg', {}).get('signal', '-'),
            inds.get('m2_yoy', {}).get('value', '-'),
            inds.get('ah_premium', {}).get('value', '-'), inds.get('ah_premium', {}).get('signal', '-')))

    return '\n'.join(lines) if lines else '(大盘信号数据不可用)'


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

    # Collect data
    indicators = MORNING_INDICATORS if session == 'morning' else EVENING_INDICATORS
    snapshot = _collect_data_snapshot(indicators)
    dashboard_snapshot = _collect_dashboard_snapshot()

    if session == 'morning':
        prompt = MORNING_PROMPT.format(date=today_str, data_snapshot=snapshot, dashboard_snapshot=dashboard_snapshot)
    else:
        prompt = EVENING_PROMPT.format(date=today_str, data_snapshot=snapshot, dashboard_snapshot=dashboard_snapshot)

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
