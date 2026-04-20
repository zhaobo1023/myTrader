# -*- coding: utf-8 -*-

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List

from data_analyst.risk_assessment.schemas import (
    LayeredRiskResult,
    MacroRiskResult,
    RegimeRiskResult,
    SectorRiskResult,
    StockRiskResult,
    DataStatus,
    score_to_level,
)

logger = logging.getLogger(__name__)


def _query_positions(user_id: int, env: str) -> List[dict]:
    """从 user_positions 取活跃持仓。user_positions 始终在 local 库。"""
    from config.db import execute_query
    rows = list(execute_query(
        """
        SELECT user_id, stock_code, stock_name, level, shares, cost_price
        FROM user_positions
        WHERE user_id = %s AND is_active = 1
        """,
        (user_id,),
        env='local',
    ))
    return [
        {
            'user_id': r['user_id'],
            'stock_code': r['stock_code'],
            'stock_name': r['stock_name'] or r['stock_code'],
            'level': r['level'] or 'L2',
            'shares': int(r['shares']) if r['shares'] is not None else 0,
            'cost_price': float(r['cost_price']) if r['cost_price'] is not None else 0.0,
        }
        for r in rows
    ]


def _make_default_macro() -> MacroRiskResult:
    return MacroRiskResult(
        score=50.0,
        level=score_to_level(50.0),
        details={'note': '宏观评估失败，使用默认值'},
        suggestions=[],
        suggested_max_exposure=0.6,
    )


def _make_default_regime() -> RegimeRiskResult:
    return RegimeRiskResult(
        score=50.0,
        level=score_to_level(50.0),
        details={'note': '市场状态评估失败，使用默认值'},
        suggestions=[],
        market_state='',
        avg_correlation=0.0,
        high_corr_pairs=[],
    )


def _make_default_sector() -> SectorRiskResult:
    return SectorRiskResult(
        score=50.0,
        level=score_to_level(50.0),
        details={'note': '行业评估失败，使用默认值'},
        suggestions=[],
        industry_breakdown={},
        overvalued_industries=[],
    )


def _compute_overall_suggestions(
    macro_result: MacroRiskResult,
    regime_result: RegimeRiskResult,
    sector_result: SectorRiskResult,
    stocks: List[StockRiskResult],
    exec_result: dict,
    overall_score: float,
) -> List[str]:
    """根据各层结果生成综合建议。"""
    suggestions = []

    # 宏观建议
    suggestions.extend(macro_result.suggestions)

    # 市场状态建议
    suggestions.extend(regime_result.suggestions)

    # 行业建议
    suggestions.extend(sector_result.suggestions)

    # 个股止损建议
    stop_loss_stocks = [s for s in stocks if s.stop_loss_hit]
    if stop_loss_stocks:
        names = ['{} ({})'.format(s.stock_name, s.stock_code) for s in stop_loss_stocks]
        suggestions.append("以下持仓已触及止损线，建议及时处理: {}".format('、'.join(names)))

    # 高风险个股
    high_risk_stocks = [s for s in stocks if s.score >= 70 and not s.stop_loss_hit]
    if high_risk_stocks:
        names = ['{} ({})'.format(s.stock_name, s.stock_code) for s in high_risk_stocks]
        suggestions.append("以下持仓风险评分偏高，建议关注: {}".format('、'.join(names)))

    # 执行层建议
    suggestions.extend(exec_result.get('suggestions', []))

    # 综合仓位建议
    exposure = macro_result.suggested_max_exposure
    if overall_score >= 70:
        suggestions.append(
            "综合风险评分 {:.0f}，整体风险偏高，建议降低总仓位至 {:.0f}% 以内".format(
                overall_score, exposure * 100
            )
        )
    elif overall_score >= 50:
        suggestions.append(
            "综合风险评分 {:.0f}，风险中等，保持当前仓位，注意动态调整".format(overall_score)
        )
    else:
        suggestions.append(
            "综合风险评分 {:.0f}，整体风险可控，可适当持有".format(overall_score)
        )

    # 去重，保留顺序
    seen = set()
    deduped = []
    for s in suggestions:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    return deduped


def scan_portfolio_v2(user_id: int, env: str = 'online') -> LayeredRiskResult:
    """完整分层风控扫描，串联 L1-L5。"""
    scan_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    logger.info("开始风控扫描 user_id=%d env=%s time=%s", user_id, env, scan_time)

    # ---- 1. 获取持仓 ----
    positions = []
    try:
        positions = _query_positions(user_id, env)
        logger.info("获取到 %d 条活跃持仓", len(positions))
    except Exception as e:
        logger.error("获取持仓失败: %s", e)

    position_codes = [p['stock_code'] for p in positions]

    # ---- 2. 数据依赖检查 ----
    data_status: List[DataStatus] = []
    try:
        from data_analyst.risk_assessment.data_deps import DataDependencyChecker
        data_status = DataDependencyChecker(env=env).check_and_trigger()
    except Exception as e:
        logger.error("数据依赖检查失败: %s", e)

    # ---- 3-5. L1/L2/L3 并行评估（三层互相独立）----
    macro_result = _make_default_macro()
    regime_result = _make_default_regime()
    sector_result = _make_default_sector()

    def _run_macro():
        from data_analyst.risk_assessment.assessors.macro import MacroRiskAssessor
        return MacroRiskAssessor(env=env).assess()

    def _run_regime():
        from data_analyst.risk_assessment.assessors.regime import RegimeRiskAssessor
        return RegimeRiskAssessor(env=env).assess(position_codes)

    def _run_sector():
        from data_analyst.risk_assessment.assessors.sector import SectorRiskAssessor
        return SectorRiskAssessor(env=env).assess(positions)

    layer_tasks = {'L1': _run_macro, 'L2': _run_regime, 'L3': _run_sector}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(fn): name for name, fn in layer_tasks.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                result = future.result()
                if name == 'L1':
                    macro_result = result
                    logger.info("L1 宏观风险分: %.1f (%s)", macro_result.score, macro_result.level)
                elif name == 'L2':
                    regime_result = result
                    logger.info("L2 市场状态分: %.1f (%s)", regime_result.score, regime_result.level)
                else:
                    sector_result = result
                    logger.info("L3 行业暴露分: %.1f (%s)", sector_result.score, sector_result.level)
            except Exception as e:
                logger.error("%s 评估失败: %s", name, e)

    # ---- 6. L4 个股风险 ----
    stocks: List[StockRiskResult] = []
    try:
        from data_analyst.risk_assessment.assessors.stock import StockFundamentalAssessor
        stocks = StockFundamentalAssessor(env=env).assess_batch(positions)
        triggered = sum(1 for s in stocks if s.stop_loss_hit or s.score >= 70)
        logger.info("L4 个股评估完成: %d 只, %d 只触发预警", len(stocks), triggered)
    except Exception as e:
        logger.error("L4 个股评估失败: %s", e)

    # ---- 7. L5 交易执行规则 ----
    exec_result = {
        'score': 50.0,
        'level': 'HIGH',
        'position_count': len(positions),
        'max_positions': 10,
        'single_position_limit': 0.30,
        'daily_loss_pct': 0.0,
        'st_stocks': [],
        'price_limit_stocks': [],
        'alerts': [],
        'suggestions': ['执行层评估失败，使用默认值'],
    }
    try:
        from data_analyst.risk_assessment.assessors.execution import ExecutionRiskAssessor
        exec_result = ExecutionRiskAssessor(env=env).assess(
            positions, macro_result=macro_result
        )
        logger.info("L5 执行规则分: %.1f (%s)", exec_result['score'], exec_result['level'])
    except Exception as e:
        logger.error("L5 执行规则评估失败: %s", e)

    # ---- 8. 综合评分 ----
    stocks_avg = (
        round(sum(s.score for s in stocks) / len(stocks), 2)
        if stocks else 50.0
    )

    overall_score = round(
        macro_result.score * 0.25
        + regime_result.score * 0.20
        + sector_result.score * 0.20
        + stocks_avg * 0.25
        + exec_result['score'] * 0.10,
        2,
    )
    logger.info(
        "综合风险分: %.1f (macro=%.1f regime=%.1f sector=%.1f stocks_avg=%.1f exec=%.1f)",
        overall_score,
        macro_result.score,
        regime_result.score,
        sector_result.score,
        stocks_avg,
        exec_result['score'],
    )

    # ---- 9. 综合建议 ----
    overall_suggestions = _compute_overall_suggestions(
        macro_result, regime_result, sector_result, stocks, exec_result, overall_score
    )

    # ---- 10. 组装结果 ----
    return LayeredRiskResult(
        scan_time=scan_time,
        user_id=user_id,
        data_status=data_status,
        macro=macro_result,
        regime=regime_result,
        sector=sector_result,
        stocks=stocks,
        overall_score=overall_score,
        overall_suggestions=overall_suggestions,
    )
