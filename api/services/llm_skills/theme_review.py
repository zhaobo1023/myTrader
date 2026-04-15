"""
ThemeReviewSkill (M2-T4): LLM-driven stock thesis review for an existing theme pool.

For each stock in the theme, the LLM evaluates whether the original investment
thesis still holds and assigns one of three verdicts:
  - hold  : thesis intact, keep in pool
  - watch : weakening signals, monitor closely
  - exit  : thesis broken, consider removing

SSE event sequence:
  start -> loading_stocks -> reviewing -> review_result -> done (or error)
"""
import json
import logging

from api.services.llm_skills.base import LLMSkillBase, SkillMeta
from api.services.llm_skills.registry import register
from api.services.llm_client_factory import get_llm_client, llm_call_with_retry
from config.db import execute_query

logger = logging.getLogger('myTrader.theme_review')

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VERDICTS: dict[str, str] = {
    'hold': '维持',
    'watch': '关注',
    'exit': '建议移出',
}

_REVIEW_SYSTEM = """你是 A 股主题投资专家，负责复评主题票池中每只成分股的投资逻辑是否仍然成立。

对每只股票，给出以下三种结论之一：
- hold  ：主题逻辑完整，建议继续持有
- watch ：逻辑有所弱化，需持续关注
- exit  ：主题逻辑已破，建议移出

输出严格 JSON（不加任何额外文字）：
{{
  "reviews": [
    {{
      "stock_code": "000001.SZ",
      "verdict": "hold|watch|exit",
      "reason": "一句话评估理由，限 60 字以内"
    }}
  ]
}}"""

_REVIEW_USER = """主题名称：{theme_name}

以下是当前票池中的成分股（共 {total} 只），请逐一复评：

{stock_list}

请对每只股票给出复评结论（hold/watch/exit）和简短理由。"""


# ---------------------------------------------------------------------------
# Skill
# ---------------------------------------------------------------------------

@register
class ThemeReviewSkill(LLMSkillBase):
    """M2 技能：主题复评，对已有票池成分股逐一评估投资逻辑。"""

    @property
    def meta(self) -> SkillMeta:
        return SkillMeta(
            skill_id='theme-review',
            name='主题复评',
            version='1.0.0',
            description='对主题票池中的成分股进行 LLM 投资逻辑复评，输出维持/关注/建议移出结论',
        )

    def __init__(self, model_alias: str | None = None):
        self._llm_factory = get_llm_client(model_alias)

    async def stream(self, theme_id: int, theme_name: str = '', **kwargs):
        """Async generator: yields SSE event dicts.

        Args:
            theme_id: ID of the theme pool to review.
            theme_name: Display name (optional, used in prompt).
        """
        try:
            async for event in self._run(theme_id, theme_name):
                yield event
        except Exception as e:
            logger.exception('[ThemeReviewSkill] unexpected error theme_id=%s', theme_id)
            yield {'type': 'error', 'message': str(e)}

    async def _run(self, theme_id: int, theme_name: str):
        yield {'type': 'start', 'message': f'正在复评主题票池（ID={theme_id}）...'}

        # Load stocks
        yield {'type': 'loading_stocks', 'message': '正在加载成分股...'}
        stocks = await self._load_stocks(theme_id)

        if not stocks:
            yield {'type': 'review_result', 'reviews': [], 'total': 0}
            yield {
                'type': 'done',
                'summary': '票池为空，无需复评',
                'hold_count': 0,
                'watch_count': 0,
                'exit_count': 0,
            }
            return

        yield {'type': 'reviewing', 'total': len(stocks), 'message': f'正在让 AI 复评 {len(stocks)} 只股票...'}

        # Build prompt
        stock_list_text = '\n'.join(
            f"{s['stock_code']} {s['stock_name']}  入池理由: {s.get('reason', '无')}"
            f"  当前得分: {s.get('total_score', 'N/A')}"
            for s in stocks
        )
        prompt = _REVIEW_USER.format(
            theme_name=theme_name or f'主题ID={theme_id}',
            total=len(stocks),
            stock_list=stock_list_text,
        )

        # LLM call
        reviews = await self._call_llm(prompt, stocks)

        # Count verdicts
        counts = {'hold': 0, 'watch': 0, 'exit': 0}
        for r in reviews:
            v = r.get('verdict', 'hold')
            if v in counts:
                counts[v] += 1

        yield {'type': 'review_result', 'reviews': reviews, 'total': len(reviews)}
        yield {
            'type': 'done',
            'summary': (
                f'复评完成：维持 {counts["hold"]} 只，关注 {counts["watch"]} 只，'
                f'建议移出 {counts["exit"]} 只'
            ),
            'hold_count': counts['hold'],
            'watch_count': counts['watch'],
            'exit_count': counts['exit'],
        }

    async def _call_llm(self, prompt: str, stocks: list[dict]) -> list[dict]:
        """Call LLM and parse review results; fallback to hold on parse error."""
        try:
            resp = await llm_call_with_retry(
                self._llm_factory.call,
                validate_json=False,
                timeout_sec=60.0,
                prompt=prompt,
                system_prompt=_REVIEW_SYSTEM,
                temperature=0.2,
                max_tokens=4096,
            )
            # extract JSON
            from api.services.theme_llm_service import ThemeCreateSkill
            raw = ThemeCreateSkill._extract_json(resp)
            data = json.loads(raw)
            reviews = data.get('reviews', [])
            # filter to valid verdicts
            valid = []
            for r in reviews:
                if r.get('verdict') not in VERDICTS:
                    r['verdict'] = 'hold'
                valid.append(r)
            return valid
        except Exception as e:
            logger.warning('[ThemeReviewSkill] LLM parse failed: %s — fallback to hold', e)
            return [
                {
                    'stock_code': s['stock_code'],
                    'verdict': 'hold',
                    'reason': '(LLM 解析失败，默认维持)',
                }
                for s in stocks
            ]

    async def _load_stocks(self, theme_id: int) -> list[dict]:
        """Load theme stocks from DB with latest score and entry reason."""
        rows = execute_query(
            """
            SELECT
                tps.stock_code,
                tps.stock_name,
                tps.reason,
                COALESCE(sc.total_score, 0) AS total_score
            FROM theme_pool_stocks tps
            LEFT JOIN (
                SELECT theme_stock_id, total_score
                FROM theme_pool_scores
                WHERE (theme_stock_id, score_date) IN (
                    SELECT theme_stock_id, MAX(score_date)
                    FROM theme_pool_scores
                    GROUP BY theme_stock_id
                )
            ) sc ON sc.theme_stock_id = tps.id
            WHERE tps.theme_id = %s
            ORDER BY total_score DESC
            """,
            (theme_id,),
            env='online',
        )
        return [dict(r) for r in rows]
