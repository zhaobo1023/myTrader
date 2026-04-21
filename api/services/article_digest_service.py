# -*- coding: utf-8 -*-
"""
Article Digest Service -- two-stage LLM filtering + curated report.

Data flow:
  wechat2rss res.db -> export script (rule filter) -> JSON file
    -> Stage A: LLM粗筛 (分类+评级+一句话) -> A/B级文章
    -> Stage B: LLM深度提炼 (结构化摘要, 事实/观点分离) -> DB
    -> Report: 交叉验证+去重+价值排序 -> Feishu doc + bot card

Key design principles:
  - 区分事实(fact)和观点(opinion), 标注清楚
  - 有数据支撑 > 有逻辑推演 > 纯观点
  - 该丢就丢, 不制造认知负担
  - 交叉验证: 多源一致才更有价值
"""
import asyncio
import json
import logging
import os
from datetime import date, datetime
from typing import Optional

from config.db import execute_query, execute_update

logger = logging.getLogger('myTrader.article_digest')

# ---------------------------------------------------------------------------
# Push category classification
# ---------------------------------------------------------------------------

PUSH_CATEGORY_MACRO = 'macro'
PUSH_CATEGORY_BROKER = 'broker'
PUSH_CATEGORY_OTHER = 'other'

# feed_name -> push_category mapping
FEED_CATEGORY_MAP: dict[str, str] = {
    # -- macro --
    'Barrons巴伦': PUSH_CATEGORY_MACRO,
    'capitalwatch': PUSH_CATEGORY_MACRO,
    'invest wallstreet': PUSH_CATEGORY_MACRO,
    'tuzhuxi': PUSH_CATEGORY_MACRO,
    '一瑜中的': PUSH_CATEGORY_MACRO,
    '坦途宏观': PUSH_CATEGORY_MACRO,
    '培风客': PUSH_CATEGORY_MACRO,
    '宏观边际MacroMargin': PUSH_CATEGORY_MACRO,
    '远川投资评论': PUSH_CATEGORY_MACRO,
    # -- broker --
    '中泰证券研究': PUSH_CATEGORY_BROKER,
    '华泰证券': PUSH_CATEGORY_BROKER,
    '国泰海通证券研究': PUSH_CATEGORY_BROKER,
    '招商证券策略研究': PUSH_CATEGORY_BROKER,
    # -- panqian (晨报聚合) --
    '盘前早咖': PUSH_CATEGORY_MACRO,
    # -- news (财经新闻快讯) --
    '财联社': PUSH_CATEGORY_MACRO,
    '界面新闻': PUSH_CATEGORY_OTHER,
    '华尔街见闻': PUSH_CATEGORY_MACRO,
    '第一财经': PUSH_CATEGORY_MACRO,
    '证券时报': PUSH_CATEGORY_BROKER,
    '中国证券报': PUSH_CATEGORY_BROKER,
    '上海证券报': PUSH_CATEGORY_BROKER,
    '经济观察报': PUSH_CATEGORY_MACRO,
    # -- other: 未列出的默认归入 other --
}

# Fallback: LLM article_type -> push_category
_TYPE_CATEGORY_FALLBACK: dict[str, str] = {
    'macro': PUSH_CATEGORY_MACRO,
}


def classify_push_category(feed_name: str, article_type: str = '') -> str:
    """Classify article into macro / broker / other by feed_name first, then article_type fallback."""
    if feed_name in FEED_CATEGORY_MAP:
        return FEED_CATEGORY_MAP[feed_name]
    return _TYPE_CATEGORY_FALLBACK.get(article_type, PUSH_CATEGORY_OTHER)


# Default path for exported articles
# Docker container maps ./output -> /app/output, server uses /root/app/output
DEFAULT_EXPORT_DIR = os.getenv(
    'ARTICLE_EXPORT_DIR',
    '/app/output/article_export' if os.path.exists('/app/output') else '/root/app/output/article_export',
)


# ---------------------------------------------------------------------------
# 1. Load exported articles from JSON
# ---------------------------------------------------------------------------

def load_exported_articles(target_date: str = None, export_dir: str = DEFAULT_EXPORT_DIR) -> list[dict]:
    """Load pre-filtered articles from wechat2rss export JSON."""
    if target_date is None:
        target_date = str(date.today())

    filepath = os.path.join(export_dir, '{}.json'.format(target_date))
    if not os.path.exists(filepath):
        logger.warning('[DIGEST] Export file not found: %s', filepath)
        return []

    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    articles = data.get('articles', [])
    logger.info('[DIGEST] Loaded %d articles from %s (raw=%d, short=%d, blacklist=%d, limit=%d)',
                len(articles), filepath,
                data.get('total_raw', 0), data.get('filtered_short', 0),
                data.get('filtered_blacklist', 0), data.get('filtered_limit', 0))
    return articles


# ---------------------------------------------------------------------------
# 2. Stage A: LLM粗筛 -- 分类 + 评级 + 一句话摘要
# ---------------------------------------------------------------------------

_STAGE_A_SYSTEM = """你是一位资深投资研究员, 负责快速评估文章的投资价值。

请对给出的文章做以下判断, 输出严格JSON（不要包裹在```json```中）:
{
  "grade": "A|B|C|D",
  "category": "macro|sector|strategy|company|market|fund|other",
  "relevance": "high|medium|low",
  "one_liner": "一句话核心观点（不超过40字）",
  "has_data": true/false,
  "is_factual": true/false,
  "reason": "评级理由（10字内）"
}

评级标准:
- A: 有独特数据/逻辑, 能指导操作 (如行业深度、宏观数据点评、策略回测)
- B: 有参考价值的观点, 但缺乏数据支撑 (如市场情绪分析、板块点评)
- C: 泛泛而谈, 人云亦云, 或信息已反映在价格中
- D: 与投资无关, 或纯广告/水文

分类:
- macro: 宏观经济/政策
- sector: 行业/板块分析
- strategy: 投资策略/方法论
- company: 个股/公司分析
- market: 市场整体研判/择时
- fund: 基金/ETF
- other: 其他

注意: is_factual=true 表示文章主要是陈述事实/数据, is_factual=false 表示主要是观点/推测
不使用任何emoji"""


async def _stage_a_classify(content: str, title: str, source: str) -> dict:
    """Stage A: quick classification and grading."""
    from api.services.llm_client_factory import get_llm_client, llm_call_with_retry

    prompt = '来源: {}\n标题: {}\n\n{}'.format(source, title, content)
    factory = get_llm_client()

    raw = await llm_call_with_retry(
        factory.call,
        prompt=prompt,
        system_prompt=_STAGE_A_SYSTEM,
        temperature=0.2,
        max_tokens=300,
        validate_json=True,
        timeout_sec=30.0,
    )
    return json.loads(raw)


# ---------------------------------------------------------------------------
# 3. Stage B: LLM深度提炼 -- 仅对A/B级文章
# ---------------------------------------------------------------------------

_STAGE_B_SYSTEM = """你是一位资深投资研究员, 负责从文章中提炼高价值信息。

严格区分事实和观点。输出严格JSON（不要包裹在```json```中）:
{
  "title": "文章标题",
  "facts": [
    {"fact": "具体事实描述（必须有数字或明确表述）", "category": "macro|sector|company"}
  ],
  "views": [
    {"view": "观点描述", "direction": "bullish|bearish|neutral", "sectors": ["板块"], "confidence": "high|medium|low"}
  ],
  "data_points": ["关键数据点（带具体数字）"],
  "risks": ["风险因素"],
  "actionable": true/false,
  "summary": "2句话概括（突出信息增量, 不要重复人尽皆知的内容）"
}

核心规则:
1. facts 必须是文章中明确陈述的客观事实, 不得推断
2. views 必须是作者明确表达的观点, 标注方向和置信度
3. 如果文章全是泛泛观点没有数据支撑, facts 和 data_points 填空列表
4. actionable=true 仅当文章提供了可操作的具体建议（如买入/卖出/调仓方向）
5. summary 必须有信息增量, 不要写"市场震荡""板块分化"之类正确的废话
6. facts 最多5条, views 最多3条, data_points 最多5条
7. 不使用任何emoji"""


async def _stage_b_deep_extract(content: str, title: str, source: str) -> dict:
    """Stage B: deep extraction for A/B grade articles."""
    from api.services.llm_client_factory import get_llm_client, llm_call_with_retry

    prompt = '来源: {}\n标题: {}\n\n{}'.format(source, title, content)
    factory = get_llm_client()

    raw = await llm_call_with_retry(
        factory.call,
        prompt=prompt,
        system_prompt=_STAGE_B_SYSTEM,
        temperature=0.2,
        max_tokens=800,
        validate_json=True,
        timeout_sec=45.0,
    )
    return json.loads(raw)


# ---------------------------------------------------------------------------
# 4. Two-stage digest pipeline
# ---------------------------------------------------------------------------

async def run_two_stage_digest(
    target_date: str = None,
    export_dir: str = DEFAULT_EXPORT_DIR,
) -> dict:
    """
    Run two-stage LLM filtering on exported articles.

    Stage A: classify all articles -> keep A/B grade
    Stage B: deep extract A/B articles -> save to DB

    Returns:
        {'stage_a': {'total': N, 'a': N, 'b': N, 'c': N, 'd': N},
         'stage_b': {'deep_extracted': N, 'saved': N, 'errors': N}}
    """
    if target_date is None:
        target_date = str(date.today())

    articles = load_exported_articles(target_date, export_dir)
    if not articles:
        return {'stage_a': {'total': 0}, 'stage_b': {'deep_extracted': 0, 'saved': 0, 'errors': 0}}

    # Check existing source_ids to skip
    existing_ids = set()
    try:
        rows = execute_query(
            "SELECT source_id FROM trade_article_digest WHERE article_date = %s",
            (target_date,), env='online',
        )
        existing_ids = {r['source_id'] for r in rows if r.get('source_id')}
    except Exception:
        pass

    # Stage A: classify all
    logger.info('[DIGEST] Stage A: classifying %d articles...', len(articles))
    graded = []
    grade_counts = {'A': 0, 'B': 0, 'C': 0, 'D': 0}

    for article in articles:
        aid = str(article.get('article_id', ''))
        if aid and aid in existing_ids:
            continue

        content = article.get('content', '')
        if len(content) < 500:
            continue

        try:
            result = await _stage_a_classify(
                content[:5000],  # Truncate for speed
                article.get('title', ''),
                article.get('feed_name', ''),
            )
            grade = result.get('grade', 'C')
            grade_counts[grade] = grade_counts.get(grade, 0) + 1

            if grade in ('A', 'B'):
                graded.append({
                    'article': article,
                    'grade': grade,
                    'category': result.get('category', 'other'),
                    'one_liner': result.get('one_liner', ''),
                    'has_data': result.get('has_data', False),
                    'is_factual': result.get('is_factual', False),
                    'reason': result.get('reason', ''),
                })

        except Exception as e:
            logger.error('[DIGEST] Stage A failed for %s: %s',
                         article.get('title', '?')[:40], e)
            grade_counts['D'] = grade_counts.get('D', 0) + 1

    logger.info('[DIGEST] Stage A done: A=%d B=%d C=%d D=%d (total=%d)',
                grade_counts['A'], grade_counts['B'], grade_counts['C'],
                grade_counts['D'], len(articles))

    # Stage B: deep extract A/B articles
    logger.info('[DIGEST] Stage B: deep extracting %d A/B articles...', len(graded))
    saved = 0
    errors = 0

    for item in graded:
        article = item['article']
        content = article.get('content', '')

        try:
            digest = await _stage_b_deep_extract(
                content[:6000],
                article.get('title', ''),
                article.get('feed_name', ''),
            )

            # Save to DB
            source_id = str(article.get('article_id', ''))
            feed_name = article.get('feed_name', '')
            push_cat = classify_push_category(feed_name, item['category'])
            one_liner = item.get('one_liner', '') or ''
            execute_update(
                """INSERT INTO trade_article_digest
                   (article_date, digest_date, source_id, source_url, title,
                    source_name, article_type, grade, digest_json, summary,
                    one_liner, push_category)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE
                    grade = VALUES(grade),
                    digest_json = VALUES(digest_json),
                    summary = VALUES(summary),
                    title = VALUES(title),
                    one_liner = VALUES(one_liner),
                    push_category = VALUES(push_category)
                """,
                (
                    target_date,
                    str(date.today()),
                    source_id or None,
                    article.get('url', '')[:500],
                    digest.get('title', article.get('title', ''))[:200],
                    feed_name[:100],
                    item['category'][:30],
                    item['grade'],
                    json.dumps(digest, ensure_ascii=False),
                    digest.get('summary', item.get('one_liner', ''))[:2000],
                    one_liner[:500],
                    push_cat,
                ),
                env='online',
            )
            saved += 1
            logger.info('[DIGEST] B [%s] %s: %s',
                        item['grade'], article.get('feed_name', ''),
                        digest.get('summary', '')[:60])

        except Exception as e:
            logger.error('[DIGEST] Stage B failed for %s: %s',
                         article.get('title', '?')[:40], e)
            errors += 1

    return {
        'stage_a': {'total': len(articles), **grade_counts},
        'stage_b': {'deep_extracted': len(graded), 'saved': saved, 'errors': errors},
    }


# ---------------------------------------------------------------------------
# 5. Curated report -- cross-validation + dedup + value ranking
# ---------------------------------------------------------------------------

_REPORT_SYSTEM_MACRO = """你是一位资深宏观经济研究主编, 负责编写每日宏观深度精选报告。

你将收到多篇宏观相关文章的结构化摘要（已区分事实和观点）。请交叉验证、去重、精选，输出一份深度宏观报告。

## 输出格式（Markdown）

### 核心数据与事实

今日最重要的宏观数据点和政策事实（必须有数字）。
- **[来源]** 事实描述（带数字）

### 深度解读

对上述事实的深层含义进行解读:
- 政策影响链条推演（A政策 -> B影响 -> C结果）
- 跨市场关联分析（如: 美债利率 -> 汇率 -> A股资金面）
- 与历史类似情景的对比

### 多空观点

编号列出各家核心观点, 标注方向:
- 编号. **[看多/看空/中性] 观点** -- 来源, 置信度, 论据

### 风险与不确定性

2-4条关键风险因素。

### 编辑点评

3-5句话: 今日宏观主线? 市场预期差在哪? 需要持续跟踪什么?

### 推荐深入阅读

从所有文章中选出1-2篇最值得花时间精读的原文。
- **[来源] 文章标题** -- 推荐理由（1句话）
  链接: [原文标题](URL)

## 严格规则
1. 不编造数据, 所有数字必须来自原文
2. 观点必须标注来源(公众号名)
3. 区分事实和观点
4. 多源一致只保留信息最丰富的, 注明"(多家一致)"
5. 不使用任何emoji
6. 允许更长篇幅(1200字以内), 保留独特视角和逻辑推演
7. 无有价值内容的模块可省略"""


_REPORT_SYSTEM_BROKER = """你是一位资深卖方研究主编, 负责编写每日券商观点精选报告。

你将收到多篇券商研报/分析师观点的结构化摘要。请提取核心观点、论据支撑、研判时间线，输出一份高密度观点报告。

## 输出格式（Markdown）

### 核心观点提取

按行业/主题分组, 每条观点包含:
- **[来源] 观点** -- 方向(看多/看空/中性)
  - 论据支撑: 具体数据或逻辑
  - 盈利预测/目标价（如有）

### 对比分析

同一标的/行业的不同券商观点对比:
- 预期差: 市场共识 vs 独特观点
- 历史对比: 与上一轮周期的异同

### 未来研判时间线

按时间维度整理关键节点:
- 近期(1-2周): 关注什么?
- 中期(1-3月): 什么逻辑会验证?
- 长期: 结构性趋势判断

### 风险提示

2-4条关键风险。

### 推荐深入阅读

从所有文章中选出1-2篇最值得精读的原文。
- **[来源] 文章标题** -- 推荐理由（1句话）
  链接: [原文标题](URL)

## 严格规则
1. 不编造数据, 所有数字必须来自原文
2. 观点必须标注来源(公众号名)
3. 对比分析要客观, 不偏向任何一方
4. 多源一致只保留信息最丰富的, 注明"(多家一致)"
5. 不使用任何emoji
6. 报告控制在1000字以内
7. 无有价值内容的模块可省略"""


_REPORT_SYSTEM_OTHER = """你是一位资深财经编辑, 负责编写每日热点速递报告。

你将收到多篇财经媒体/自媒体文章的结构化摘要。请提取热点事件、捕捉市场情绪、判断影响面, 输出一份简洁明快的速递。

## 输出格式（Markdown）

### 热点事件

今日最重要的市场事件/消息（按重要性排序）:
- **[来源] 事件描述** -- 影响面判断(利好/利空/中性, 影响哪些板块)

### 市场情绪

综合各方观点, 判断当前市场情绪:
- 主流情绪: 乐观/悲观/分歧?
- 资金动向信号（如有）
- 板块轮动线索（如有）

### 值得关注

2-3条短期可能发酵的线索或催化剂。

### 推荐深入阅读

1-2篇最值得精读的原文。
- **[来源] 文章标题** -- 推荐理由（1句话）
  链接: [原文标题](URL)

## 严格规则
1. 不编造数据, 所有数字必须来自原文
2. 观点必须标注来源(公众号名)
3. 简洁明快, 每条热点控制在2句话以内
4. 不使用任何emoji
5. 报告控制在600字以内, 宁缺毋滥
6. 无有价值内容的模块可省略"""


# Per-category report configuration
_CATEGORY_REPORT_CONFIG = {
    PUSH_CATEGORY_MACRO: {
        'title_prefix': '宏观深度',
        'system_prompt': _REPORT_SYSTEM_MACRO,
        'card_color': 'blue',
        'max_tokens': 2500,
    },
    PUSH_CATEGORY_BROKER: {
        'title_prefix': '券商观点',
        'system_prompt': _REPORT_SYSTEM_BROKER,
        'card_color': 'purple',
        'max_tokens': 2048,
    },
    PUSH_CATEGORY_OTHER: {
        'title_prefix': '热点速递',
        'system_prompt': _REPORT_SYSTEM_OTHER,
        'card_color': 'turquoise',
        'max_tokens': 1500,
    },
}


# ---------------------------------------------------------------------------
# Combined report prompt (replaces per-category reports at runtime)
# ---------------------------------------------------------------------------

_REPORT_SYSTEM_COMBINED = """你是一位资深财经编辑主编, 负责编写每日投资精选报告。

你将收到当日A/B级文章的结构化摘要(已区分事实和观点), 来源包括宏观研究、券商研报、财经自媒体等。
请交叉验证、去重、按维度重组, 输出一份高信息密度的综合报告。

## 输出格式(Markdown)

### 宏观与政策
提炼当日最重要的宏观数据和政策变化(必须有具体数字)。
对数据做简要解读: 影响链条、历史对比、对投资的含义。多源提及同一数据只保留最完整的版本, 标注"(多家一致)"。

### 行业与公司
按主题聚合行业观点和公司动态:
- 每个主题用粗体标题, 下列事实+观点+操作含义
- 对同一标的的不同观点做对比(如看多vs看空)
- 标注方向和置信度

### 市场情绪与事件
今日盘面/市场最显著的特征和热点事件。
判断主流情绪、资金动向信号、板块轮动线索。
简洁明快, 每条控制在2句话以内。

### 综合研判
3-5句话收尾: 今日信息的核心主线是什么? 市场预期差在哪? 未来1-2周需要跟踪什么?

### 风险清单
3-5条去重后的关键风险(合并所有来源)。

### 推荐原文
从所有文章中精选2-3篇最值得花时间精读的原文。
- **[来源] 标题** -- 推荐理由(1句话)
  链接: [标题](URL)

## 严格规则
1. 不编造数据, 所有数字必须来自原文
2. 观点必须标注来源(公众号名)
3. 多源一致只保留信息最丰富的版本, 注明"(多家一致)"
4. 不使用任何emoji字符
5. 全文控制在2000字以内
6. 无有价值内容的模块可省略
7. 区分事实和观点, 事实带数据, 观点标方向"""


_REPORT_SYSTEM_WEEKEND = """你是一位资深财经编辑主编, 负责编写周末投资精选报告。

你将收到当日A/B级公众号文章的结构化摘要(已区分事实和观点)。
注意: 今天是周末, 市场休市, 不需要涉及盘面走势、当日行情、资金动向等交易数据。
请专注于提炼文章中有长期价值的深度思考和研究内容。

## 输出格式(Markdown)

### 深度研究与洞察
提炼本周最有价值的深度分析文章核心观点:
- 产业趋势、技术变革、政策走向等中长期视角
- 独特的分析框架或方法论
- 有数据支撑的深度研究结论

### 宏观与政策回顾
本周重要的宏观数据、政策变化及其深层含义:
- 关键数据点(必须有具体数字)
- 政策解读与影响链条推演
- 国际形势与地缘变化

### 行业与公司
值得关注的行业趋势和公司动态:
- 按主题聚合, 标注方向和置信度
- 重点关注结构性变化而非短期波动

### 思考与启发
从文章中提炼的投资智慧和方法论:
- 值得学习的分析视角
- 可能改变认知的观点
- 需要持续关注的长期线索

### 推荐原文
从所有文章中精选2-3篇最值得花时间精读的原文。
- **[来源] 标题** -- 推荐理由(1句话)
  链接: [标题](URL)

## 严格规则
1. 不编造数据, 所有数字必须来自原文
2. 观点必须标注来源(公众号名)
3. 不涉及当日盘面走势、交易行情、资金动向等实时数据
4. 不使用任何emoji字符
5. 全文控制在2000字以内
6. 无有价值内容的模块可省略
7. 区分事实和观点, 事实带数据, 观点标方向"""


def _is_weekend(target_date: str) -> bool:
    """Check if target_date (YYYY-MM-DD) is Saturday or Sunday."""
    dt = datetime.strptime(target_date, '%Y-%m-%d')
    return dt.weekday() >= 5  # 5=Saturday, 6=Sunday


def _build_digest_prompt(target_date: str, rows: list) -> str:
    """Build LLM prompt from digest rows (shared by all categories)."""
    sections = []
    for i, row in enumerate(rows, 1):
        dj = row.get('digest_json') or {}
        if isinstance(dj, str):
            try:
                dj = json.loads(dj)
            except Exception:
                dj = {}

        s = '--- 文章{} ---\n'.format(i)
        s += '来源: {}\n'.format(row.get('source_name', ''))
        s += '标题: {}\n'.format(row.get('title', ''))
        s += '链接: {}\n'.format(row.get('source_url', ''))
        s += '评级: {}\n'.format(row.get('grade', ''))

        facts = dj.get('facts', [])
        if facts:
            s += '事实:\n'
            for f in facts:
                s += '  - [事实] {} ({})\n'.format(f.get('fact', ''), f.get('category', ''))

        views = dj.get('views', [])
        if views:
            s += '观点:\n'
            for v in views:
                s += '  - [观点/{}] {} (板块: {}, 置信度: {})\n'.format(
                    v.get('direction', '?'),
                    v.get('view', ''),
                    ', '.join(v.get('sectors', [])),
                    v.get('confidence', ''),
                )

        data_pts = dj.get('data_points', [])
        if data_pts:
            s += '数据: {}\n'.format(' | '.join(data_pts[:5]))

        risks = dj.get('risks', [])
        if risks:
            s += '风险: {}\n'.format(' | '.join(risks))

        summary = dj.get('summary', row.get('summary', ''))
        if summary:
            s += '摘要: {}\n'.format(summary)

        sections.append(s)

    return '今日日期: {}\n收录文章数: {} (A/B级)\n\n{}'.format(
        target_date, len(rows), '\n'.join(sections))


async def _generate_single_category_report(
    target_date: str,
    category: str,
    rows: list,
) -> dict:
    """Generate and publish a single category report to Feishu."""
    from api.services.llm_client_factory import get_llm_client
    from api.services.feishu_doc_publisher import publish_briefing, _send_card

    cfg = _CATEGORY_REPORT_CONFIG[category]
    prompt = _build_digest_prompt(target_date, rows)

    factory = get_llm_client()
    content = await factory.call(
        prompt=prompt,
        system_prompt=cfg['system_prompt'],
        temperature=0.5,
        max_tokens=cfg['max_tokens'],
    )

    if not content or len(content) < 50:
        raise RuntimeError('LLM returned empty report for category: {}'.format(category))

    title = '{} {}'.format(cfg['title_prefix'], target_date)
    doc = publish_briefing(title=title, content=content)

    _send_card(
        title=title,
        verdict='{}篇文章精选'.format(len(rows)),
        doc_url=doc['url'],
        color=cfg['card_color'],
    )

    logger.info('[REPORT] Published %s: %s -> %s (%d articles)',
                category, title, doc['url'], len(rows))

    return {
        'category': category,
        'date': target_date,
        'content': content,
        'article_count': len(rows),
        'document_id': doc['document_id'],
        'url': doc['url'],
    }


_CATEGORY_LABEL = {
    PUSH_CATEGORY_MACRO: '宏观类文章',
    PUSH_CATEGORY_BROKER: '券商类文章',
    PUSH_CATEGORY_OTHER: '热点类文章',
}


async def _generate_combined_report(
    target_date: str,
    grouped: dict[str, list],
) -> dict:
    """Generate a single combined report from all categories, publish to Feishu."""
    from api.services.llm_client_factory import get_llm_client
    from api.services.feishu_doc_publisher import publish_briefing, _send_card

    # Build unified prompt with category labels
    all_sections = []
    total_count = 0
    for category in (PUSH_CATEGORY_MACRO, PUSH_CATEGORY_BROKER, PUSH_CATEGORY_OTHER):
        cat_rows = grouped.get(category)
        if not cat_rows:
            continue
        total_count += len(cat_rows)
        label = _CATEGORY_LABEL.get(category, category)
        cat_prompt = _build_digest_prompt(target_date, cat_rows)
        all_sections.append('## {}\n\n{}'.format(label, cat_prompt))

    if not all_sections:
        raise RuntimeError('No articles to generate combined report')

    prompt = '\n\n'.join(all_sections)

    # Use weekend-specific prompt on Sat/Sun (no market data references)
    weekend = _is_weekend(target_date)
    system_prompt = _REPORT_SYSTEM_WEEKEND if weekend else _REPORT_SYSTEM_COMBINED

    factory = get_llm_client()
    content = await factory.call(
        prompt=prompt,
        system_prompt=system_prompt,
        temperature=0.5,
        max_tokens=3500,
    )

    if not content or len(content) < 50:
        raise RuntimeError('LLM returned empty combined report')

    title = '周末精选 {}'.format(target_date) if weekend else '每日投资精选 {}'.format(target_date)
    doc = publish_briefing(title=title, content=content)

    _send_card(
        title=title,
        verdict='{}篇文章综合精选'.format(total_count),
        doc_url=doc['url'],
        color='blue',
    )

    logger.info('[REPORT] Published combined report: %s -> %s (%d articles)',
                title, doc['url'], total_count)

    # Persist to DB
    try:
        execute_update(
            """INSERT INTO trade_article_report
               (report_date, report_type, title, content,
                article_count, document_id, doc_url)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON DUPLICATE KEY UPDATE
                content = VALUES(content),
                article_count = VALUES(article_count),
                document_id = VALUES(document_id),
                doc_url = VALUES(doc_url),
                created_at = NOW()""",
            (target_date, 'combined', title, content,
             total_count, doc['document_id'], doc['url']),
            env='online',
        )
        logger.info('[REPORT] Saved combined report to DB for %s', target_date)
    except Exception as e:
        logger.error('[REPORT] Failed to save report to DB: %s', e)

    # Push to inbox for all active users
    try:
        from api.services.inbox_service import create_system_broadcast
        inbox_content = content
        if doc.get('url'):
            inbox_content += '\n\n---\n飞书原文: {}'.format(doc['url'])
        create_system_broadcast(
            title, inbox_content,
            message_type='daily_report',
            metadata={'doc_url': doc.get('url', ''), 'article_count': total_count},
            env='online',
        )
        logger.info('[REPORT] Pushed combined report to inbox')
    except Exception as e:
        logger.error('[REPORT] Failed to push to inbox: %s', e)

    return {
        'category': 'combined',
        'date': target_date,
        'content': content,
        'article_count': total_count,
        'document_id': doc['document_id'],
        'url': doc['url'],
    }


async def generate_categorized_reports(
    target_date: str = None,
) -> list[dict]:
    """Generate a combined curated report from all category digests, publish to Feishu."""
    if target_date is None:
        target_date = str(date.today())

    # Load all A/B grade digests with push_category
    rows = execute_query(
        """SELECT title, source_name, article_type, grade, digest_json,
                  summary, source_url, push_category
           FROM trade_article_digest
           WHERE article_date = %s AND grade IN ('A', 'B')
           ORDER BY FIELD(grade, 'A', 'B'), id""",
        (target_date,), env='online',
    )

    if not rows:
        raise RuntimeError('No A/B grade digests for {}'.format(target_date))

    # Group by push_category (NULL -> other)
    grouped: dict[str, list] = {}
    for row in rows:
        cat = row.get('push_category') or PUSH_CATEGORY_OTHER
        grouped.setdefault(cat, []).append(row)

    logger.info('[REPORT] Categories: %s',
                {k: len(v) for k, v in grouped.items()})

    # Generate combined report (single doc covering all categories)
    results = []
    try:
        result = await _generate_combined_report(target_date, grouped)
        results.append(result)
    except Exception as e:
        logger.error('[REPORT] Failed to generate combined report: %s', e)

    # Mark all as used
    execute_update(
        "UPDATE trade_article_digest SET used_in_report = 1 WHERE article_date = %s AND grade IN ('A', 'B')",
        (target_date,), env='online',
    )

    return results


# Keep legacy function for backward compatibility
async def generate_curated_report(
    target_date: str = None,
) -> dict:
    """Generate curated report -- now delegates to categorized reports."""
    results = await generate_categorized_reports(target_date)
    if not results:
        raise RuntimeError('No reports generated')
    # Return first report for backward compat
    return results[0]


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def get_relevant_digests(session: str = 'morning', lookback_days: int = 1) -> list[dict]:
    """
    Return recent A/B-grade digests with non-empty one_liner for briefing injection.

    Args:
        session: 'morning' or 'evening' (currently unused, reserved for
                 future session_relevance filtering)
        lookback_days: how many days back to search

    Returns:
        list of dicts with keys: source, one_liner, grade, article_type
    """
    from datetime import timedelta
    cutoff = (date.today() - timedelta(days=lookback_days)).strftime('%Y-%m-%d')

    rows = execute_query(
        """SELECT source_name, one_liner, grade, article_type
           FROM trade_article_digest
           WHERE article_date >= %s
             AND grade IN ('A', 'B')
             AND one_liner IS NOT NULL AND one_liner != ''
           ORDER BY FIELD(grade, 'A', 'B'), id DESC
           LIMIT 8""",
        (cutoff,), env='online',
    )

    return [
        {
            'source': r.get('source_name', ''),
            'one_liner': r.get('one_liner', ''),
            'grade': r.get('grade', ''),
            'article_type': r.get('article_type', ''),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# 6. Full pipeline (23:00 cron)
# ---------------------------------------------------------------------------

async def run_nightly_digest_pipeline(
    target_date: str = None,
    export_dir: str = DEFAULT_EXPORT_DIR,
) -> dict:
    """
    Full pipeline:
    1. Load exported articles (from wechat2rss export script)
    2. Two-stage LLM filtering (classify -> deep extract)
    3. Generate curated report -> Feishu

    Note: The export script should be run BEFORE this pipeline.
    On server: python3 /root/app/scripts/export_wechat_articles.py
    """
    if target_date is None:
        target_date = str(date.today())

    logger.info('[PIPELINE] Starting nightly digest for %s', target_date)

    # Step 1+2: Two-stage digest
    digest_result = await run_two_stage_digest(
        target_date=target_date,
        export_dir=export_dir,
    )

    # Step 3: Generate categorized reports (one per category)
    try:
        report_results = await generate_categorized_reports(target_date=target_date)
    except RuntimeError as e:
        logger.warning('[PIPELINE] Report skipped: %s', e)
        return {
            'status': 'partial',
            'digest': digest_result,
            'reports': [],
            'reason': str(e),
        }

    return {
        'status': 'ok',
        'digest': digest_result,
        'reports': [
            {
                'category': r.get('category'),
                'url': r.get('url'),
                'article_count': r.get('article_count'),
            }
            for r in report_results
        ],
    }
