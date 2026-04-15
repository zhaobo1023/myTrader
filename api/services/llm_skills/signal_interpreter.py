"""
SignalInterpreterSkill (M3-T2): LLM-driven technical signal interpretation.

Reads tech indicators for a stock and produces a natural-language investment summary.

SSE event sequence:
  start -> loading_signals -> interpreting -> interpretation -> done (or error)
"""
import json
import logging
from typing import Optional

from api.services.llm_skills.base import LLMSkillBase, SkillMeta
from api.services.llm_skills.registry import register
from api.services.llm_client_factory import get_llm_client, llm_call_with_retry
from config.db import execute_query

logger = logging.getLogger('myTrader.signal_interpreter')

VALID_STANCES = {'bullish', 'bearish', 'neutral'}

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_INTERP_SYSTEM = """你是 A 股技术面分析专家，根据技术指标数据给出清晰的自然语言投研摘要。

输出严格 JSON（不加任何额外文字）：
{
  "stance": "bullish|bearish|neutral",
  "summary": "综合判断摘要，100字以内",
  "key_signals": ["关键信号1", "关键信号2"],
  "risk_factors": ["风险点1"],
  "suggested_action": "具体操作建议，50字以内"
}

stance 定义：
- bullish：多头信号占优，可考虑布局
- bearish：空头信号占优，注意风险
- neutral：多空信号混杂，观望为主"""

_INTERP_USER = """股票：{stock_code} {stock_name}

技术指标（最新交易日）：
- 收盘价: {close}  MA5: {ma5}  MA20: {ma20}  MA60: {ma60}
- MACD: {macd}  Signal: {macd_signal}  Hist: {macd_hist}
- RSI(14): {rsi14}
- 量比: {volume_ratio}x
- 近5日涨跌: {return_5d:+.1f}%  近20日涨跌: {return_20d:+.1f}%
- RPS(20): {rps_20}  综合评分: {total_score}

请给出技术面综合判断。"""


# ---------------------------------------------------------------------------
# Skill
# ---------------------------------------------------------------------------

@register
class SignalInterpreterSkill(LLMSkillBase):
    """M3 技能：技术信号解读，将量化指标转为自然语言投研摘要。"""

    @property
    def meta(self) -> SkillMeta:
        return SkillMeta(
            skill_id='signal-interpreter',
            name='信号解读',
            version='1.0.0',
            description='将技术面信号与评分转为自然语言投研摘要，支持看多/看空/中性判断',
        )

    def __init__(self, model_alias: str | None = None):
        self._llm_factory = get_llm_client(model_alias)

    async def stream(self, stock_code: str, **kwargs):
        try:
            async for event in self._run(stock_code):
                yield event
        except Exception as e:
            logger.exception('[SignalInterpreterSkill] unexpected error stock=%s', stock_code)
            yield {'type': 'error', 'message': str(e)}

    async def _run(self, stock_code: str):
        yield {'type': 'start', 'message': f'正在解读 {stock_code} 技术信号...'}

        yield {'type': 'loading_signals', 'message': '正在加载技术指标...'}
        signals = await self._load_signals(stock_code)

        if signals is None:
            yield {'type': 'error', 'message': f'未找到 {stock_code} 的技术数据，请确认代码正确且数据库已更新。'}
            return

        yield {'type': 'interpreting', 'message': '正在让 AI 解读信号...'}
        interpretation = await self._call_llm(signals)

        yield {
            'type': 'interpretation',
            'stock_code': stock_code,
            'stock_name': signals.get('stock_name', ''),
            'stance': interpretation.get('stance', 'neutral'),
            'summary': interpretation.get('summary', ''),
            'key_signals': interpretation.get('key_signals', []),
            'risk_factors': interpretation.get('risk_factors', []),
            'suggested_action': interpretation.get('suggested_action', ''),
            'signals_snapshot': {
                'close': signals.get('close'),
                'ma5': signals.get('ma5'),
                'ma20': signals.get('ma20'),
                'rsi14': signals.get('rsi14'),
                'macd_hist': signals.get('macd_hist'),
                'volume_ratio': signals.get('volume_ratio'),
                'return_5d': signals.get('return_5d'),
                'return_20d': signals.get('return_20d'),
                'rps_20': signals.get('rps_20'),
                'total_score': signals.get('total_score'),
            },
        }
        yield {'type': 'done', 'summary': interpretation.get('summary', '解读完成')}

    async def _call_llm(self, signals: dict) -> dict:
        def _f(key, default=0):
            v = signals.get(key)
            return v if v is not None else default

        prompt = _INTERP_USER.format(
            stock_code=signals.get('stock_code', ''),
            stock_name=signals.get('stock_name', ''),
            close=_f('close'),
            ma5=_f('ma5'), ma20=_f('ma20'), ma60=_f('ma60'),
            macd=_f('macd'), macd_signal=_f('macd_signal'), macd_hist=_f('macd_hist'),
            rsi14=_f('rsi14'),
            volume_ratio=_f('volume_ratio', 1.0),
            return_5d=_f('return_5d'),
            return_20d=_f('return_20d'),
            rps_20=_f('rps_20'),
            total_score=_f('total_score'),
        )

        try:
            resp = await llm_call_with_retry(
                self._llm_factory.call,
                validate_json=False,
                timeout_sec=30.0,
                prompt=prompt,
                system_prompt=_INTERP_SYSTEM,
                temperature=0.2,
                max_tokens=1024,
            )
            from api.services.theme_llm_service import ThemeCreateSkill
            raw = ThemeCreateSkill._extract_json(resp)
            data = json.loads(raw)
            # Ensure stance is valid
            if data.get('stance') not in VALID_STANCES:
                data['stance'] = 'neutral'
            return data
        except Exception as e:
            logger.warning('[SignalInterpreterSkill] LLM parse failed: %s', e)
            return {
                'stance': 'neutral',
                'summary': '(AI 解读暂时不可用，请稍后重试)',
                'key_signals': [],
                'risk_factors': [],
                'suggested_action': '',
            }

    async def _load_signals(self, stock_code: str) -> Optional[dict]:
        """Load latest tech indicators for a stock from DB."""
        rows = execute_query(
            """
            SELECT
                i.stock_code,
                b.stock_name,
                i.close,
                i.ma5, i.ma20, i.ma60,
                i.macd, i.macd_signal, i.macd_hist,
                i.rsi_14 AS rsi14,
                i.volume_ratio,
                i.return_5d, i.return_20d,
                COALESCE(r.rps_20, 0) AS rps_20,
                COALESCE(s.total_score, 0) AS total_score
            FROM trade_stock_indicators i
            LEFT JOIN trade_stock_basic b ON b.stock_code = i.stock_code
            LEFT JOIN trade_stock_daily_basic r
                ON r.stock_code = i.stock_code AND r.trade_date = i.trade_date
            LEFT JOIN (
                SELECT tps.stock_code, tsc.total_score
                FROM theme_pool_stocks tps
                JOIN (
                    SELECT theme_stock_id, total_score
                    FROM theme_pool_scores
                    WHERE (theme_stock_id, score_date) IN (
                        SELECT theme_stock_id, MAX(score_date) FROM theme_pool_scores GROUP BY theme_stock_id
                    )
                ) tsc ON tsc.theme_stock_id = tps.id
                WHERE tps.stock_code = %s
                LIMIT 1
            ) s ON s.stock_code = i.stock_code
            WHERE i.stock_code = %s
            ORDER BY i.trade_date DESC
            LIMIT 1
            """,
            (stock_code, stock_code),
            env='online',
        )
        if not rows:
            return None
        r = rows[0]
        return {k: (float(v) if v is not None and isinstance(v, (int, float)) else v)
                for k, v in r.items()}
