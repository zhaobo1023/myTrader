"""
PortfolioDoctorSkill (M3-T1): LLM-driven portfolio health check.

Analyzes holdings concentration, industry exposure, and suggests rebalancing.

SSE event sequence:
  start -> loading -> analyzing -> diagnosis -> done (or error)
"""
import json
import logging
from dataclasses import dataclass
from typing import Optional

from api.services.llm_skills.base import LLMSkillBase, SkillMeta
from api.services.llm_skills.registry import register
from api.services.llm_client_factory import get_llm_client, llm_call_with_retry
from config.db import execute_query

logger = logging.getLogger('myTrader.portfolio_doctor')

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class HoldingItem:
    stock_code: str
    stock_name: str
    industry: str
    weight: float        # percentage 0-100
    cost: float
    current_price: float
    pnl_pct: float


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

def compute_concentration(holdings: list[HoldingItem]) -> dict:
    """Compute portfolio concentration metrics from holdings list."""
    if not holdings:
        return {
            'stock_count': 0,
            'top3_weight': 0.0,
            'max_single_weight': 0.0,
            'industry_distribution': {},
        }

    sorted_by_weight = sorted(holdings, key=lambda h: h.weight, reverse=True)
    top3_weight = sum(h.weight for h in sorted_by_weight[:3])
    max_single_weight = sorted_by_weight[0].weight if sorted_by_weight else 0.0

    # Industry distribution (weight sum per industry)
    industry_map: dict[str, float] = {}
    total_weight = sum(h.weight for h in holdings) or 1.0
    for h in holdings:
        industry_map[h.industry] = industry_map.get(h.industry, 0.0) + h.weight

    # Normalize to percentage of total
    industry_pct = {k: round(v / total_weight * 100, 1) for k, v in industry_map.items()}

    return {
        'stock_count': len(holdings),
        'top3_weight': round(top3_weight, 1),
        'max_single_weight': round(max_single_weight, 1),
        'industry_distribution': industry_pct,
    }


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_DOCTOR_SYSTEM = """你是专业的 A 股投资组合顾问，擅长分析持仓结构并提供调仓建议。

输出严格 JSON（不加任何额外文字）：
{
  "summary": "一段话总结组合健康状态（100字以内）",
  "risks": ["风险点1", "风险点2"],
  "suggestions": [
    {
      "action": "减持|增持|分散|观察",
      "stock_code": "000001.SZ 或 null（泛建议时为 null）",
      "reason": "一句话理由，限50字"
    }
  ]
}"""

_DOCTOR_USER = """请分析以下持仓组合，给出健康诊断和调仓建议。

持仓概况：
- 持仓数量：{stock_count} 只
- TOP3 权重占比：{top3_weight}%
- 最大单票权重：{max_single_weight}%
- 行业分布：{industry_dist}

持仓明细：
{holdings_text}

请重点关注：集中度风险、行业轮动、盈亏结构。"""


# ---------------------------------------------------------------------------
# Skill
# ---------------------------------------------------------------------------

@register
class PortfolioDoctorSkill(LLMSkillBase):
    """M3 技能：持仓健诊，分析集中度风险并给出调仓建议。"""

    @property
    def meta(self) -> SkillMeta:
        return SkillMeta(
            skill_id='portfolio-doctor',
            name='持仓健诊',
            version='1.0.0',
            description='分析持仓集中度、行业风险敞口，LLM 给出调仓建议',
        )

    def __init__(self, model_alias: str | None = None):
        self._llm_factory = get_llm_client(model_alias)

    async def stream(self, user_id: int, **kwargs):
        try:
            async for event in self._run(user_id):
                yield event
        except Exception as e:
            logger.exception('[PortfolioDoctorSkill] unexpected error user_id=%s', user_id)
            yield {'type': 'error', 'message': str(e)}

    async def _run(self, user_id: int):
        yield {'type': 'start', 'message': '正在分析持仓健康状况...'}

        yield {'type': 'loading', 'message': '正在加载持仓数据...'}
        holdings = await self._load_holdings(user_id)

        concentration = compute_concentration(holdings)
        yield {'type': 'analyzing', 'message': f'共 {len(holdings)} 只持仓，正在让 AI 诊断...', 'concentration': concentration}

        diagnosis = await self._call_llm(holdings, concentration)

        yield {
            'type': 'diagnosis',
            'summary': diagnosis.get('summary', ''),
            'risks': diagnosis.get('risks', []),
            'suggestions': diagnosis.get('suggestions', []),
            'concentration': concentration,
        }
        yield {
            'type': 'done',
            'summary': diagnosis.get('summary', '诊断完成'),
        }

    async def _call_llm(self, holdings: list[HoldingItem], concentration: dict) -> dict:
        if not holdings:
            return {'summary': '当前持仓为空，无需诊断。', 'risks': [], 'suggestions': []}

        holdings_text = '\n'.join(
            f"  {h.stock_code} {h.stock_name}  行业:{h.industry}  权重:{h.weight:.1f}%  盈亏:{h.pnl_pct:+.1f}%"
            for h in holdings[:30]
        )
        industry_dist = '  '.join(f"{k}:{v}%" for k, v in concentration['industry_distribution'].items())

        prompt = _DOCTOR_USER.format(
            stock_count=concentration['stock_count'],
            top3_weight=concentration['top3_weight'],
            max_single_weight=concentration['max_single_weight'],
            industry_dist=industry_dist or '数据不足',
            holdings_text=holdings_text,
        )

        try:
            resp = await llm_call_with_retry(
                self._llm_factory.call,
                validate_json=False,
                timeout_sec=30.0,
                prompt=prompt,
                system_prompt=_DOCTOR_SYSTEM,
                temperature=0.3,
                max_tokens=2048,
            )
            from api.services.theme_llm_service import ThemeCreateSkill
            raw = ThemeCreateSkill._extract_json(resp)
            return json.loads(raw)
        except Exception as e:
            logger.warning('[PortfolioDoctorSkill] LLM parse failed: %s', e)
            return {
                'summary': '(AI 分析暂时不可用，请稍后重试)',
                'risks': [],
                'suggestions': [],
            }

    async def _load_holdings(self, user_id: int) -> list[HoldingItem]:
        """Load active holdings from portfolio_mgmt_stocks table."""
        rows = execute_query(
            """
            SELECT stock_code, stock_name, industry,
                   weight, cost_price AS cost, current_price,
                   COALESCE((current_price - cost_price) / NULLIF(cost_price, 0) * 100, 0) AS pnl_pct
            FROM portfolio_mgmt_stocks
            WHERE status = 'active'
            ORDER BY weight DESC
            """,
            env='online',
        )
        return [
            HoldingItem(
                stock_code=r['stock_code'],
                stock_name=r['stock_name'],
                industry=r.get('industry') or '未知',
                weight=float(r.get('weight') or 0),
                cost=float(r.get('cost') or 0),
                current_price=float(r.get('current_price') or 0),
                pnl_pct=float(r.get('pnl_pct') or 0),
            )
            for r in rows
        ]
