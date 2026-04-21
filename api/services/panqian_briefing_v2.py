# -*- coding: utf-8 -*-
"""
Panqian Briefing V2 -- morning briefing derived from "Panqian Zaoka" (盘前早咖) wechat articles.

Pipeline:
  1. Fetch today's "盘前早咖" article from trade_article_digest (or raw export JSON)
  2. Stage A: LLM extracts structured items (each line/paragraph -> typed information)
  3. Stage B: LLM re-processes items with value scoring, then writes an enhanced briefing
  4. Publish to Feishu doc + bot card (parallel with V1)

The result is stored in trade_briefing with session='morning_v2'.
"""
import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Optional

from config.db import execute_query, execute_update
from api.services.llm_client_factory import get_llm_client

logger = logging.getLogger('myTrader.panqian_v2')

PANQIAN_FEED_NAME = '盘前早咖'
DEFAULT_EXPORT_DIR = os.getenv(
    'ARTICLE_EXPORT_DIR',
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), 'output', 'article_export'),
)

# ---------------------------------------------------------------------------
# Stage A prompt -- extract structured items from raw article
# ---------------------------------------------------------------------------

_STAGE_A_SYSTEM = """你是一位专业的财经信息拆解专家。

你的任务是：把"盘前早咖"公众号的晨报原文，逐条拆解成结构化信息条目。

## 输出格式（JSON数组，不要有多余文字）

```json
[
  {
    "type": "macro" | "sector" | "stock" | "policy" | "overseas" | "risk" | "other",
    "content": "信息原文（保留关键数字和专有名词）",
    "data_points": ["具体数据1", "具体数据2"],
    "direction": "bullish" | "bearish" | "neutral",
    "tickers": ["行业/板块/股票名称"],
    "source_hint": "文章中提到的来源（如有）"
  }
]
```

## 拆解规则
1. 每一条独立的信息/论断拆成一个条目，不要合并，不要遗漏
2. 只提取文章里明确写出来的信息，不要推断或补充
3. data_points 只填文章里出现的具体数字（指数点位、涨跌幅、资金量、PE等）
4. 没有明确数字的条目 data_points 填空数组
5. tickers 填文章提到的板块/行业/个股名称，A股格式（如"人工智能"、"光伏"、"贵州茅台"）
6. 不使用任何emoji，用纯文本
7. 如果文章内容少于3条有效信息，输出空数组 []"""

_STAGE_A_USER = """请拆解以下"盘前早咖"晨报原文：

---
{article_content}
---

直接输出JSON数组，不要任何额外说明。"""


# ---------------------------------------------------------------------------
# Stage B prompt -- value scoring + enhanced briefing generation
# ---------------------------------------------------------------------------

_STAGE_B_SYSTEM = """你是一位专业的A股投资顾问，擅长从外部资讯中提炼有价值的投资线索。

你将收到从"盘前早咖"晨报中提取的结构化信息条目，你的任务是：
1. 对每条信息进行价值评分
2. 综合高价值信息，生成一份增强版晨报（V2版本）

## 价值评分标准（1-5分）
- 5分：有具体数据支撑的操作线索（如板块资金流向+涨停数量+催化剂三要素齐全）
- 4分：有部分数据支撑的方向判断（如指数位置+量能特征）
- 3分：有逻辑推演的观点（如政策解读+行业影响链条）
- 2分：方向正确但缺乏依据（如"看好科技板块"无数据）
- 1分：泛泛而谈或已是旧闻

## 输出格式（强制5层结构，Markdown）

### 一句话研判
一句话给出市场立场。格式: **偏多/偏空/中性（高/中/低置信）**

### 核心信号（来自盘前早咖）
列出3-5条评分4分及以上的高价值信息，格式：
- [类型] 信息内容（附具体数字）

### 今日关注方向
基于上述信号，提炼2-3个今日值得跟踪的板块/方向，每个方向说明：
- 驱动因素是什么
- 数据支撑程度如何（强/中/弱）
- 追高风险提示

### 需要验证的线索
列出1-2条有价值但需要进一步验证的信息（评分3分），说明验证方向。

### 风险提示
基于文章内容，列出1-2条今日操作需要警惕的事项。

## 强制规则
1. 不使用任何emoji，用[风险]、[机会]、[关注]等纯文本标记
2. 不编造文章中没有的数据
3. 不给出具体仓位建议
4. 标注数据来源为"盘前早咖"
5. 全文控制在500字以内
6. 报告末尾注明: 数据来源: 盘前早咖公众号 | 日期: {date}"""

_STAGE_B_USER = """以下是从"盘前早咖"晨报（{date}）提取的结构化条目：

{items_json}

请对每条进行价值评分，然后输出增强版晨报V2。"""


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def _fetch_panqian_article(target_date: date = None) -> Optional[dict]:
    """
    Fetch the latest 盘前早咖 article for target_date.

    Tries two sources in order:
    1. Raw export JSON file (primary -- full original content, best for Stage A extraction)
    2. trade_article_digest table (fallback -- digest_json already structured, skip Stage A)

    Returns dict with keys: title, content, source, date
    Extra key 'pre_extracted_items' (list) is set when source=db_digest, allowing
    generate_v2_briefing() to skip Stage A and feed items directly to Stage B.
    """
    if target_date is None:
        target_date = date.today()

    date_str = target_date.strftime('%Y-%m-%d')

    # Source 1: Raw export JSON (preferred -- full original text, no information loss)
    try:
        # Try today's file first, then yesterday (script may run just after midnight)
        for candidate_date in [date_str, (target_date - timedelta(days=1)).strftime('%Y-%m-%d')]:
            json_path = os.path.join(DEFAULT_EXPORT_DIR, '{}.json'.format(candidate_date))
            if not os.path.exists(json_path):
                continue
            with open(json_path, encoding='utf-8') as f:
                data = json.load(f)
            for art in data.get('articles', []):
                if art.get('feed_name') == PANQIAN_FEED_NAME:
                    content = art.get('content', '')
                    if content:
                        logger.info('[panqian_v2] Loaded from export JSON: %s', art.get('title', ''))
                        return {
                            'title': art.get('title', ''),
                            'content': content,
                            'source': 'export_json',
                            'date': date_str,
                        }
    except Exception as e:
        logger.debug('[panqian_v2] Export JSON fetch failed: %s', e)

    # Source 2: DB digest table (fallback -- content is already structured, skip Stage A)
    try:
        rows = execute_query(
            """SELECT title, digest_json, article_date
               FROM trade_article_digest
               WHERE source_name = %s AND article_date >= %s
               ORDER BY article_date DESC, id DESC
               LIMIT 1""",
            (PANQIAN_FEED_NAME, (target_date - timedelta(days=2)).strftime('%Y-%m-%d')),
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
                # Convert digest_json structure directly into Stage-A-compatible items
                # so Stage A can be skipped entirely -- avoids double abstraction loss
                pre_items = []
                for f in (dj.get('facts') or []):
                    text = f.get('fact', '') if isinstance(f, dict) else str(f)
                    if text:
                        pre_items.append({'type': 'macro', 'content': text,
                                          'data_points': [], 'direction': 'neutral', 'tickers': []})
                for v in (dj.get('views') or []):
                    text = v.get('view', '') if isinstance(v, dict) else str(v)
                    direction = v.get('direction', 'neutral') if isinstance(v, dict) else 'neutral'
                    if text:
                        pre_items.append({'type': 'sector', 'content': text,
                                          'data_points': [], 'direction': direction, 'tickers': []})
                for p in (dj.get('data_points') or []):
                    pre_items.append({'type': 'macro', 'content': str(p),
                                      'data_points': [str(p)], 'direction': 'neutral', 'tickers': []})
                if pre_items:
                    logger.info('[panqian_v2] Loaded from DB digest (pre-extracted %d items): %s',
                                len(pre_items), row.get('title', ''))
                    return {
                        'title': row.get('title', ''),
                        'content': '',  # not needed; pre_extracted_items will be used
                        'source': 'db_digest',
                        'date': str(row.get('article_date', date_str)),
                        'pre_extracted_items': pre_items,
                    }
    except Exception as e:
        logger.debug('[panqian_v2] DB fetch failed: %s', e)

    logger.warning('[panqian_v2] No 盘前早咖 article found for %s', date_str)
    return None


# ---------------------------------------------------------------------------
# Stage A: extract structured items
# ---------------------------------------------------------------------------

async def _extract_items(article_content: str) -> list:
    """Call LLM to extract structured items from raw article. Returns list of dicts."""
    llm = get_llm_client()
    prompt = _STAGE_A_USER.format(article_content=article_content[:6000])
    raw = await llm.call(
        prompt=prompt,
        system_prompt=_STAGE_A_SYSTEM,
        temperature=0.1,
        max_tokens=3000,
    )

    # Strip markdown code fences if present (handles ```json\n...\n``` variants)
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
        logger.warning('[panqian_v2] Stage A JSON parse failed, raw=%s', raw[:200])
        items = []

    logger.info('[panqian_v2] Stage A extracted %d items', len(items))
    return items


# ---------------------------------------------------------------------------
# Stage B: value scoring + enhanced briefing
# ---------------------------------------------------------------------------

async def _generate_v2_content(items: list, target_date: date) -> str:
    """Call LLM to score items and generate V2 briefing markdown."""
    date_str = target_date.strftime('%Y-%m-%d')
    llm = get_llm_client()

    items_json = json.dumps(items, ensure_ascii=False, indent=2)
    prompt = _STAGE_B_USER.format(date=date_str, items_json=items_json)
    system = _STAGE_B_SYSTEM.format(date=date_str)

    content = await llm.call(
        prompt=prompt,
        system_prompt=system,
        temperature=0.3,
        max_tokens=2000,
    )
    logger.info('[panqian_v2] Stage B generated %d chars', len(content))
    return content


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

SESSION_V2 = 'morning_v2'


def _load_v2_briefing(brief_date: str) -> Optional[str]:
    """Load cached V2 briefing from trade_briefing table."""
    rows = execute_query(
        "SELECT content FROM trade_briefing WHERE session = %s AND brief_date = %s",
        (SESSION_V2, brief_date),
        env='online',
    )
    return rows[0]['content'] if rows else None


def _save_v2_briefing(brief_date: str, content: str, meta: dict = None) -> None:
    """Persist V2 briefing to trade_briefing table."""
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
    logger.info('[panqian_v2] Saved V2 briefing for %s', brief_date)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def generate_v2_briefing(force: bool = False) -> dict:
    """
    Generate V2 morning briefing from 盘前早咖 article.

    Returns:
        {
            'date': str,
            'content': str,
            'cached': bool,
            'items_count': int,
            'article_source': str,  # 'db_digest' | 'export_json' | 'none'
        }
    """
    today = date.today()
    today_str = today.strftime('%Y-%m-%d')

    # Check cache
    if not force:
        cached = _load_v2_briefing(today_str)
        if cached:
            logger.info('[panqian_v2] Returning cached V2 briefing for %s', today_str)
            return {
                'date': today_str,
                'content': cached,
                'cached': True,
                'items_count': 0,
                'article_source': 'cache',
            }

    # Fetch source article
    article = _fetch_panqian_article(today)
    if not article:
        msg = '[V2速递中止] 未找到盘前早咖 {} 的文章，请确认公众号已订阅并已运行导出脚本。'.format(today_str)
        return {
            'date': today_str,
            'content': msg,
            'cached': False,
            'items_count': 0,
            'article_source': 'none',
        }

    # Stage A: extract items (skip if DB source already provided pre-extracted items)
    pre_items = article.get('pre_extracted_items')
    if pre_items:
        items = pre_items
        logger.info('[panqian_v2] Stage A skipped (DB source, %d pre-extracted items)', len(items))
    else:
        items = await _extract_items(article['content'])
    if not items:
        msg = '[V2速递中止] 盘前早咖文章内容解析为空，原文长度={}字'.format(len(article['content']))
        return {
            'date': today_str,
            'content': msg,
            'cached': False,
            'items_count': 0,
            'article_source': article['source'],
        }

    # Stage B: generate enhanced briefing
    content = await _generate_v2_content(items, today)

    # Persist
    meta = {
        'version': 1,
        'source': article['source'],
        'article_title': article.get('title', ''),
        'items_count': len(items),
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    try:
        _save_v2_briefing(today_str, content, meta)
    except Exception as e:
        logger.warning('[panqian_v2] Failed to save V2 briefing: %s', e)

    return {
        'date': today_str,
        'content': content,
        'cached': False,
        'items_count': len(items),
        'article_source': article['source'],
    }
