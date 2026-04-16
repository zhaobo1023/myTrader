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
from datetime import date
from typing import Optional

from config.db import execute_query, execute_update

logger = logging.getLogger('myTrader.article_digest')

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
            execute_update(
                """INSERT INTO trade_article_digest
                   (article_date, digest_date, source_id, source_url, title,
                    source_name, article_type, grade, digest_json, summary)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE
                    grade = VALUES(grade),
                    digest_json = VALUES(digest_json),
                    summary = VALUES(summary),
                    title = VALUES(title)
                """,
                (
                    target_date,
                    str(date.today()),
                    source_id or None,
                    article.get('url', '')[:500],
                    digest.get('title', article.get('title', ''))[:200],
                    article.get('feed_name', '')[:100],
                    item['category'][:30],
                    item['grade'],
                    json.dumps(digest, ensure_ascii=False),
                    digest.get('summary', item.get('one_liner', ''))[:2000],
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

_REPORT_SYSTEM = """你是一位资深投资研究主编, 负责编写每日精选观点报告。

你将收到多篇文章的结构化摘要（已区分事实和观点）。请交叉验证、去重、精选，输出一份高价值报告。

## 输出格式（Markdown）

### 宏观与政策

与宏观经济、货币政策、地缘政治、贸易数据相关的事实和观点。
- 事实用: **[来源]** 事实描述（带数字）
- 观点用: 编号. **[看多/看空/中性] 观点** -- 来源, 置信度

### 行业与公司

与具体行业趋势、公司基本面、财报数据相关的内容。
- 事实用: **[来源]** 事实描述（带数字）
- 观点用: 编号. **[看多/看空/中性] 观点** -- 来源, 置信度

### 市场策略

与择时、仓位、风格切换、交易策略相关的观点。
- 编号. **观点** -- 来源, 置信度

### 风险提示

汇总去重后的风险因素, 列出2-4条。

### 编辑点评

2-3句话: 今日舆论主线是什么? 多空分歧在哪? 信息增量在哪里?

### 推荐深入阅读

从所有文章中选出1-2篇最值得花时间精读的原文。选择标准: 有独特数据/深度逻辑/反共识观点。
每条必须附带原文链接。格式:
- **[来源] 文章标题** -- 推荐理由（1句话）
  链接: [原文标题](URL)

## 严格规则
1. 不编造数据, 所有数字必须来自原文
2. 观点必须标注来源(公众号名)
3. 区分事实(客观陈述)和观点(主观判断)
4. 如果多个来源说同一件事, 只保留信息最丰富的那个, 注明"(多家一致)"
5. 该丢就丢: 人云亦云的观点、无数据支撑的情绪判断、已反映在价格中的信息
6. 不使用任何emoji
7. 报告总长度控制在800字以内, 宁缺毋滥
8. 每个模块（宏观与政策/行业与公司/市场策略）如果无有价值内容可省略，不必硬凑"""


async def generate_curated_report(
    target_date: str = None,
) -> dict:
    """Generate curated report from digests, publish to Feishu."""
    from api.services.llm_client_factory import get_llm_client

    if target_date is None:
        target_date = str(date.today())

    # Load digests (A/B grade only, ordered by grade then has_data)
    rows = execute_query(
        """SELECT title, source_name, article_type, grade, digest_json, summary, source_url
           FROM trade_article_digest
           WHERE article_date = %s AND grade IN ('A', 'B')
           ORDER BY FIELD(grade, 'A', 'B'), id""",
        (target_date,), env='online',
    )

    if not rows:
        raise RuntimeError('No A/B grade digests for {}'.format(target_date))

    # Build prompt
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

    prompt = '今日日期: {}\n收录文章数: {} (A/B级)\n\n{}'.format(
        target_date, len(rows), '\n'.join(sections))

    factory = get_llm_client()
    content = await factory.call(
        prompt=prompt,
        system_prompt=_REPORT_SYSTEM,
        temperature=0.5,
        max_tokens=2048,
    )

    if not content or len(content) < 50:
        raise RuntimeError('LLM returned empty or too short report')

    # Publish to Feishu
    from api.services.feishu_doc_publisher import publish_briefing, _send_card

    title = '精选观点 {}'.format(target_date)
    doc = publish_briefing(title=title, content=content)

    _send_card(
        title=title,
        verdict='{}篇文章精选'.format(len(rows)),
        doc_url=doc['url'],
    )

    # Mark as used
    execute_update(
        "UPDATE trade_article_digest SET used_in_report = 1 WHERE article_date = %s",
        (target_date,), env='online',
    )

    logger.info('[REPORT] Published: %s -> %s', title, doc['url'])

    return {
        'date': target_date,
        'content': content,
        'article_count': len(rows),
        'document_id': doc['document_id'],
        'url': doc['url'],
    }


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

    # Step 3: Generate curated report
    try:
        report_result = await generate_curated_report(target_date=target_date)
    except RuntimeError as e:
        logger.warning('[PIPELINE] Report skipped: %s', e)
        return {
            'status': 'partial',
            'digest': digest_result,
            'report': None,
            'reason': str(e),
        }

    return {
        'status': 'ok',
        'digest': digest_result,
        'report': {
            'url': report_result.get('url'),
            'article_count': report_result.get('article_count'),
        },
    }
