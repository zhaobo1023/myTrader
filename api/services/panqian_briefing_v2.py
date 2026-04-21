# -*- coding: utf-8 -*-
"""
社媒信号晨报 V2 -- 基于社交媒体资讯的个股深度分析晨报。

Pipeline:
  1. 获取今日社媒资讯文章（导出 JSON 优先，DB 摘要备用）
  2. Stage A: LLM 提取结构化条目，包含 tickers 字段
  3. Stage B: 查询个股技术面（trade_stock_factor + trade_stock_rps）
              + 近期公告（research_announcements）
  4. Stage C: LLM 综合生成「个股信号分析」格式晨报
  5. 写入 trade_briefing（session='morning_v2'），推送飞书

社媒来源不在报告中披露，统一以「社媒信号」标注。
"""
import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Optional

from config.db import execute_query, execute_update
from api.services.llm_client_factory import get_llm_client

logger = logging.getLogger('myTrader.panqian_v2')

# 社媒来源公众号名称（内部变量，不输出到报告）
_SOCIAL_FEED_NAME = '盘前早咖'
DEFAULT_EXPORT_DIR = os.getenv(
    'ARTICLE_EXPORT_DIR',
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), 'output', 'article_export'),
)

# ---------------------------------------------------------------------------
# Stage A prompt -- 结构化提取
# ---------------------------------------------------------------------------

_STAGE_A_SYSTEM = """你是一位专业的财经信息拆解专家。

你的任务是：把社交媒体晨报原文，逐条拆解成结构化信息条目。

## 输出格式（JSON数组，不要有多余文字）

```json
[
  {
    "type": "macro" | "sector" | "stock" | "policy" | "overseas" | "risk" | "other",
    "content": "信息原文（保留关键数字和专有名词）",
    "data_points": ["具体数据1", "具体数据2"],
    "direction": "bullish" | "bearish" | "neutral",
    "tickers": ["个股/板块/行业名称"],
    "source_hint": "文章中提到的来源（如有）"
  }
]
```

## 拆解规则
1. 每一条独立的信息/论断拆成一个条目，不要合并，不要遗漏
2. 只提取文章里明确写出来的信息，不要推断或补充
3. data_points 只填文章里出现的具体数字（指数点位、涨跌幅、资金量、PE等）
4. 没有明确数字的条目 data_points 填空数组
5. tickers 填文章提到的具体个股名称（如"天通股份"、"通鼎互联"），不填宽泛板块名
6. 不使用任何emoji，用纯文本
7. 如果文章内容少于3条有效信息，输出空数组 []"""

_STAGE_A_USER = """请拆解以下社媒晨报原文：

---
{article_content}
---

直接输出JSON数组，不要任何额外说明。"""


# ---------------------------------------------------------------------------
# Stage C prompt -- 个股深度分析 + 晨报生成
# ---------------------------------------------------------------------------

_STAGE_C_SYSTEM = """你是一位专业的A股投资顾问，擅长从社媒资讯中挖掘个股交易机会并结合技术面和消息面进行综合判断。

你将收到：
1. 从社媒晨报提取的结构化条目（包含个股名称和方向）
2. 每只个股的实时技术面数据（RSI、动量、RPS排名、MACD等）
3. 每只个股的近期重大公告（如有）

你的任务：生成一份「社媒信号晨报」，格式如下：

---

### 市场研判
一句话给出今日市场立场。格式：**偏多/偏空/中性（高/中/低置信）**

### 个股信号分析

对每只个股单独一节，格式（严格按此输出，不要省略任何字段）：

#### {{股票名称}}（{{代码}}）[{{所属板块/主题}}]

**[社媒信号]** {{社媒资讯原文提到的内容，一句话，不提来源名称}}

**[技术面]** RSI=XX（超买/中性/超卖），动量20日=XX%，RPS-20=XX/RPS-60=XX（强势/中等/偏弱），MACD=多头/空头，价格位置=XX%（低位/中位/高位）

**[消息面]** {{近7日有公告则列出类型和一句话说明；无公告则写"近7日无重大公告"}}

**[综合判断]** {{50字以内，明确说追高风险/关注机会/建议回避，附1个具体观察点}}

---（下一只个股）---

### 板块整体方向
按板块归纳，说明驱动因素和数据支撑强度（强/中/弱）。每个板块1-2句话。

### 今日操作提示
列出2-3条最重要的盘中观察点（量能、突破位、止损位等具体数字）。

### 风险提示
1-2条今日需要警惕的事项。

---

## 强制规则
1. 不使用任何emoji，用[OK]、[WARN]、[BAD]等纯文本标记
2. 不编造数据，技术面数字直接用提供的数值
3. 没有匹配到技术数据的个股，技术面写「暂无数据」
4. 全文不出现社媒来源名称，统一用「社媒信号」
5. 每只个股分析控制在150字以内，精炼输出
6. 报告末尾注明：数据来源：社媒信号 + 技术因子数据库 | 日期：{date}"""

_STAGE_C_USER = """以下是今日（{date}）社媒晨报结构化条目及个股数据：

## 社媒条目
{items_json}

## 个股技术面数据
{tech_data}

## 个股近期公告
{ann_data}

请生成社媒信号晨报。"""


# ---------------------------------------------------------------------------
# 数据获取
# ---------------------------------------------------------------------------

def _fetch_social_article(target_date: date = None) -> Optional[dict]:
    """
    获取目标日期的社媒晨报文章。
    优先读导出 JSON（原文），备用 DB 摘要（跳过 Stage A）。
    """
    if target_date is None:
        target_date = date.today()

    date_str = target_date.strftime('%Y-%m-%d')

    # 优先: 导出 JSON 原文
    try:
        for candidate_date in [date_str, (target_date - timedelta(days=1)).strftime('%Y-%m-%d')]:
            json_path = os.path.join(DEFAULT_EXPORT_DIR, '{}.json'.format(candidate_date))
            if not os.path.exists(json_path):
                continue
            with open(json_path, encoding='utf-8') as f:
                data = json.load(f)
            for art in data.get('articles', []):
                if art.get('feed_name') == _SOCIAL_FEED_NAME:
                    content = art.get('content', '')
                    if content:
                        logger.info('[v2] Loaded from export JSON: %s', art.get('title', ''))
                        return {
                            'title': art.get('title', ''),
                            'content': content,
                            'source': 'export_json',
                            'date': date_str,
                        }
    except Exception as e:
        logger.debug('[v2] Export JSON fetch failed: %s', e)

    # 备用: DB 摘要（pre_extracted_items 跳过 Stage A）
    try:
        rows = execute_query(
            """SELECT title, digest_json, article_date
               FROM trade_article_digest
               WHERE source_name = %s AND article_date >= %s
               ORDER BY article_date DESC, id DESC
               LIMIT 1""",
            (_SOCIAL_FEED_NAME, (target_date - timedelta(days=2)).strftime('%Y-%m-%d')),
            env='online',
        )
        if rows:
            row = rows[0]
            dj = row.get('digest_json')
            if isinstance(dj, str):
                try:
                    dj = json.loads(dj)
                except (json.JSONDecodeError, TypeError):
                    dj = {}
            if dj:
                pre_items = []
                for f in (dj.get('facts') or []):
                    text = f.get('fact', '') if isinstance(f, dict) else str(f)
                    if text:
                        pre_items.append({'type': 'macro', 'content': text,
                                          'data_points': [], 'direction': 'neutral', 'tickers': []})
                for v in (dj.get('views') or []):
                    text = v.get('view', '') if isinstance(v, dict) else str(v)
                    direction = v.get('direction', 'neutral') if isinstance(v, dict) else 'neutral'
                    tickers = v.get('tickers', []) if isinstance(v, dict) else []
                    if text:
                        pre_items.append({'type': 'sector', 'content': text,
                                          'data_points': [], 'direction': direction,
                                          'tickers': tickers})
                for p in (dj.get('data_points') or []):
                    pre_items.append({'type': 'macro', 'content': str(p),
                                      'data_points': [str(p)], 'direction': 'neutral', 'tickers': []})
                if pre_items:
                    logger.info('[v2] Loaded from DB digest (%d pre-extracted items): %s',
                                len(pre_items), row.get('title', ''))
                    return {
                        'title': row.get('title', ''),
                        'content': '',
                        'source': 'db_digest',
                        'date': str(row.get('article_date', date_str)),
                        'pre_extracted_items': pre_items,
                    }
    except Exception as e:
        logger.debug('[v2] DB fetch failed: %s', e)

    logger.warning('[v2] No social media article found for %s', date_str)
    return None


def _lookup_stock_codes(names: list) -> dict:
    """
    个股名称 -> 股票代码 模糊匹配。
    返回 {name: code} 字典，未匹配到则不包含该 key。
    """
    if not names:
        return {}

    result = {}
    for name in names:
        name_clean = name.strip()
        if not name_clean or len(name_clean) < 2:
            continue
        try:
            rows = execute_query(
                "SELECT stock_code, stock_name FROM trade_stock_basic WHERE stock_name LIKE %s LIMIT 1",
                ('%{}%'.format(name_clean),),
                env='online',
            )
            if rows:
                result[name_clean] = rows[0]['stock_code']
        except Exception as e:
            logger.debug('[v2] Code lookup failed for %s: %s', name_clean, e)

    logger.info('[v2] Resolved %d/%d stock names to codes', len(result), len(names))
    return result


def _fetch_tech_data(codes: list) -> dict:
    """
    批量查询个股技术因子数据。
    返回 {code: {rsi, mom20, mom60, rps20, rps60, rps120, macd, pos, close, turnover}}
    """
    if not codes:
        return {}

    placeholders = ','.join(['%s'] * len(codes))

    # trade_stock_factor
    factor_map = {}
    try:
        latest_date = execute_query(
            "SELECT MAX(calc_date) as d FROM trade_stock_factor WHERE stock_code IN ({})".format(placeholders),
            tuple(codes), env='online'
        )
        if latest_date and latest_date[0].get('d'):
            rows = execute_query(
                """SELECT stock_code, rsi_14, momentum_20d, momentum_60d, macd_signal,
                          price_position, turnover_ratio, close
                   FROM trade_stock_factor
                   WHERE stock_code IN ({}) AND calc_date = %s""".format(placeholders),
                tuple(codes) + (latest_date[0]['d'],),
                env='online',
            )
            for r in rows:
                factor_map[r['stock_code']] = {
                    'rsi': float(r['rsi_14'] or 50),
                    'mom20': float(r['momentum_20d'] or 0) * 100,
                    'mom60': float(r['momentum_60d'] or 0) * 100,
                    'macd': float(r['macd_signal'] or 0),
                    'pos': float(r['price_position'] or 0.5) * 100,
                    'turnover': float(r['turnover_ratio'] or 0),
                    'close': float(r['close'] or 0),
                }
    except Exception as e:
        logger.warning('[v2] Factor query failed: %s', e)

    # trade_stock_rps
    rps_map = {}
    try:
        latest_rps = execute_query(
            "SELECT MAX(trade_date) as d FROM trade_stock_rps WHERE stock_code IN ({})".format(placeholders),
            tuple(codes), env='online'
        )
        if latest_rps and latest_rps[0].get('d'):
            rows = execute_query(
                """SELECT stock_code, rps_20, rps_60, rps_120
                   FROM trade_stock_rps
                   WHERE stock_code IN ({}) AND trade_date = %s""".format(placeholders),
                tuple(codes) + (latest_rps[0]['d'],),
                env='online',
            )
            for r in rows:
                rps_map[r['stock_code']] = {
                    'rps20': float(r['rps_20'] or 50),
                    'rps60': float(r['rps_60'] or 50),
                    'rps120': float(r['rps_120'] or 50),
                }
    except Exception as e:
        logger.warning('[v2] RPS query failed: %s', e)

    # 合并
    result = {}
    for code in codes:
        f = factor_map.get(code, {})
        r = rps_map.get(code, {})
        if f or r:
            result[code] = {**f, **r}

    return result


def _format_tech_data(name_code_map: dict, tech_data: dict) -> str:
    """将技术数据格式化为 LLM 可读的文本块。"""
    if not name_code_map:
        return '（无个股数据）'

    lines = []
    for name, code in name_code_map.items():
        td = tech_data.get(code)
        if not td:
            lines.append('{name}（{code}）: 暂无技术数据'.format(name=name, code=code))
            continue

        rsi = td.get('rsi', 50)
        rsi_label = '超买' if rsi > 70 else ('超卖' if rsi < 30 else '中性')
        mom20 = td.get('mom20', 0)
        rps20 = td.get('rps20', 50)
        rps60 = td.get('rps60', 50)
        rps120 = td.get('rps_120', td.get('rps120', 50))
        macd = td.get('macd', 0)
        macd_label = '多头' if macd > 0 else '空头'
        pos = td.get('pos', 50)
        pos_label = '低位' if pos < 30 else ('高位' if pos > 70 else '中位')
        close = td.get('close', 0)

        lines.append(
            '{name}（{code}）: 收盘={close:.2f}, RSI={rsi:.0f}({rsi_label}), '
            '动量20日={mom20:+.1f}%, RPS-20={rps20:.0f}/RPS-60={rps60:.0f}/RPS-120={rps120:.0f}, '
            'MACD={macd_label}({macd:+.4f}), 价格位置={pos:.0f}%({pos_label})'.format(
                name=name, code=code, close=close, rsi=rsi, rsi_label=rsi_label,
                mom20=mom20, rps20=rps20, rps60=rps60, rps120=rps120,
                macd_label=macd_label, macd=macd, pos=pos, pos_label=pos_label,
            )
        )

    return '\n'.join(lines)


def _format_ann_data(name_code_map: dict, ann_data: dict) -> str:
    """将公告数据格式化为 LLM 可读文本块。"""
    if not ann_data:
        return '（所有个股近7日无重大公告）'

    lines = []
    for name, code in name_code_map.items():
        anns = ann_data.get(code, [])
        if not anns:
            lines.append('{name}（{code}）: 近7日无重大公告'.format(name=name, code=code))
        else:
            for a in anns[:3]:  # 最多3条
                lines.append('{name}（{code}）: [{date}][{type}][{direction}] {title}'.format(
                    name=name, code=code,
                    date=a['date'], type=a['type'],
                    direction=a['direction'], title=a['title'][:60],
                ))

    return '\n'.join(lines) if lines else '（所有个股近7日无重大公告）'


# ---------------------------------------------------------------------------
# Stage A: 提取结构化条目
# ---------------------------------------------------------------------------

async def _extract_items(article_content: str) -> list:
    """LLM 从原文提取结构化条目。"""
    llm = get_llm_client()
    prompt = _STAGE_A_USER.format(article_content=article_content[:6000])
    raw = await llm.call(
        prompt=prompt,
        system_prompt=_STAGE_A_SYSTEM,
        temperature=0.1,
        max_tokens=3000,
    )

    text = raw.strip()
    if text.startswith('```'):
        lines = text.split('\n')
        text = '\n'.join(lines[1:])
        if text.rstrip().endswith('```'):
            text = text.rstrip()[:-3].strip()

    try:
        items = json.loads(text)
        if not isinstance(items, list):
            items = []
    except (json.JSONDecodeError, ValueError):
        logger.warning('[v2] Stage A JSON parse failed, raw=%s', raw[:200])
        items = []

    logger.info('[v2] Stage A extracted %d items', len(items))
    return items


# ---------------------------------------------------------------------------
# Stage C: 个股深度分析 + 晨报生成
# ---------------------------------------------------------------------------

async def _generate_v2_content(items: list, name_code_map: dict,
                                tech_data: dict, ann_data: dict,
                                target_date: date) -> str:
    """LLM 综合所有数据生成完整晨报。"""
    date_str = target_date.strftime('%Y-%m-%d')
    llm = get_llm_client()

    items_json = json.dumps(items, ensure_ascii=False, indent=2)
    tech_text = _format_tech_data(name_code_map, tech_data)
    ann_text = _format_ann_data(name_code_map, ann_data)
    system = _STAGE_C_SYSTEM.format(date=date_str)

    prompt = _STAGE_C_USER.format(
        date=date_str,
        items_json=items_json[:2000],
        tech_data=tech_text,
        ann_data=ann_text,
    )

    content = await llm.call(
        prompt=prompt,
        system_prompt=system,
        temperature=0.3,
        max_tokens=2500,
    )
    logger.info('[v2] Stage C generated %d chars', len(content))
    return content


# ---------------------------------------------------------------------------
# 持久化
# ---------------------------------------------------------------------------

SESSION_V2 = 'morning_v2'


def _load_v2_briefing(brief_date: str) -> Optional[str]:
    rows = execute_query(
        "SELECT content FROM trade_briefing WHERE session = %s AND brief_date = %s",
        (SESSION_V2, brief_date),
        env='online',
    )
    return rows[0]['content'] if rows else None


def _save_v2_briefing(brief_date: str, content: str, meta: dict = None) -> None:
    sd_json = json.dumps(meta, ensure_ascii=False) if meta else None
    execute_update(
        """INSERT INTO trade_briefing (session, brief_date, content, structured_data)
           VALUES (%s, %s, %s, %s)
           ON DUPLICATE KEY UPDATE content = VALUES(content),
                                    structured_data = VALUES(structured_data),
                                    created_at = NOW()""",
        (SESSION_V2, brief_date, content, sd_json),
        env='online',
    )
    logger.info('[v2] Saved V2 briefing for %s', brief_date)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

async def generate_v2_briefing(force: bool = False) -> dict:
    """
    生成社媒信号晨报 V2。

    Returns:
        {date, content, cached, items_count, article_source, stocks_analyzed}
    """
    today = date.today()
    today_str = today.strftime('%Y-%m-%d')

    # 缓存检查
    if not force:
        cached = _load_v2_briefing(today_str)
        if cached:
            logger.info('[v2] Returning cached V2 briefing for %s', today_str)
            return {'date': today_str, 'content': cached, 'cached': True,
                    'items_count': 0, 'article_source': 'cache', 'stocks_analyzed': 0}

    # 获取社媒文章
    article = _fetch_social_article(today)
    if not article:
        msg = '[V2速递中止] 未找到社媒晨报 {} 的文章，请确认已运行导出脚本。'.format(today_str)
        return {'date': today_str, 'content': msg, 'cached': False,
                'items_count': 0, 'article_source': 'none', 'stocks_analyzed': 0}

    # Stage A: 提取条目
    pre_items = article.get('pre_extracted_items')
    if pre_items:
        items = pre_items
        logger.info('[v2] Stage A skipped (DB source, %d pre-extracted items)', len(items))
    else:
        items = await _extract_items(article['content'])

    if not items:
        msg = '[V2速递中止] 社媒文章内容解析为空，原文长度={}字'.format(len(article['content']))
        return {'date': today_str, 'content': msg, 'cached': False,
                'items_count': 0, 'article_source': article['source'], 'stocks_analyzed': 0}

    # 从条目中收集所有个股名称
    all_tickers = []
    for item in items:
        tickers = item.get('tickers', [])
        for t in tickers:
            t = t.strip()
            # 过滤掉宽泛的板块名（长度>4字 或包含"板块"/"行业"）
            if t and len(t) <= 6 and '板块' not in t and '行业' not in t and '概念' not in t:
                if t not in all_tickers:
                    all_tickers.append(t)

    # 名称 -> 代码映射
    name_code_map = _lookup_stock_codes(all_tickers)
    codes = list(name_code_map.values())

    # 查技术数据
    tech_data = _fetch_tech_data(codes) if codes else {}

    # 查近期公告
    ann_data = {}
    if codes:
        try:
            from data_analyst.fetchers.announcement_fetcher import get_announcements_for_codes
            ann_data = get_announcements_for_codes(codes, days=7)
        except Exception as e:
            logger.warning('[v2] Announcement fetch failed: %s', e)

    # Stage C: 生成晨报
    content = await _generate_v2_content(items, name_code_map, tech_data, ann_data, today)

    # 持久化
    meta = {
        'version': 2,
        'source': article['source'],
        'article_title': article.get('title', ''),
        'items_count': len(items),
        'stocks_analyzed': len(name_code_map),
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    try:
        _save_v2_briefing(today_str, content, meta)
    except Exception as e:
        logger.warning('[v2] Failed to save V2 briefing: %s', e)

    return {
        'date': today_str,
        'content': content,
        'cached': False,
        'items_count': len(items),
        'article_source': article['source'],
        'stocks_analyzed': len(name_code_map),
    }
