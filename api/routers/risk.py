# -*- coding: utf-8 -*-
"""
风控 V2 API 路由

GET /api/risk/scan           - 触发完整分层扫描，返回 LayeredRiskResult 序列化为 dict
GET /api/risk/macro          - 仅宏观层评估
GET /api/risk/report         - 返回最新 Markdown 报告字符串
POST /api/risk/trigger-deps  - 手动触发数据依赖检查
"""
import logging

from fastapi import APIRouter, Depends, HTTPException

from api.middleware.auth import get_current_user
from api.models.user import User
from data_analyst.risk_assessment.storage import dataclass_to_dict, reconstruct_layered_result

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/risk', tags=['risk'])


@router.get('/scan')
async def risk_scan_v2(
    current_user: User = Depends(get_current_user),
):
    """
    触发完整分层风控扫描（L1-L5），返回 LayeredRiskResult 序列化后的 dict。
    计算密集，耗时约 10-30 秒。
    """
    import asyncio

    def _do_scan(user_id: int):
        from data_analyst.risk_assessment.scanner import scan_portfolio_v2
        return scan_portfolio_v2(user_id=user_id, env='online')

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _do_scan, current_user.id)
        return dataclass_to_dict(result)
    except Exception as exc:
        logger.error('[RISK] scan failed for user=%s: %s', current_user.id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get('/macro')
async def risk_macro(
    current_user: User = Depends(get_current_user),
):
    """仅宏观层评估（L1），响应较快。"""
    import asyncio

    def _do_macro():
        from data_analyst.risk_assessment.assessors.macro import MacroRiskAssessor
        result = MacroRiskAssessor(env='online').assess()
        return dataclass_to_dict(result)

    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _do_macro)
    except Exception as exc:
        logger.error('[RISK] macro failed for user=%s: %s', current_user.id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get('/report')
async def risk_report(
    current_user: User = Depends(get_current_user),
):
    """
    返回最新风控扫描的 Markdown 报告字符串。
    优先从 output/risk_assessment/ 加载缓存，否则实时计算。
    """
    import asyncio

    def _do_report(user_id: int):
        from data_analyst.risk_assessment.storage import load_scan_result, reconstruct_layered_result
        from data_analyst.risk_assessment.report import generate_report_v2

        cached = load_scan_result()
        if cached is not None:
            try:
                return generate_report_v2(reconstruct_layered_result(cached))
            except Exception:
                pass

        from data_analyst.risk_assessment.scanner import scan_portfolio_v2
        return generate_report_v2(scan_portfolio_v2(user_id=user_id, env='online'))

    try:
        loop = asyncio.get_running_loop()
        report_md = await loop.run_in_executor(None, _do_report, current_user.id)
        return {'report': report_md}
    except Exception as exc:
        logger.error('[RISK] report failed for user=%s: %s', current_user.id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post('/trigger-deps')
async def trigger_deps(
    current_user: User = Depends(get_current_user),
):
    """
    手动触发数据依赖检查，返回各数据源状态列表。
    """
    import asyncio

    def _do_check():
        from data_analyst.risk_assessment.data_deps import DataDependencyChecker
        results = DataDependencyChecker(env='online').check_and_trigger()
        return dataclass_to_dict(results)

    try:
        loop = asyncio.get_running_loop()
        statuses = await loop.run_in_executor(None, _do_check)
        return {'data_status': statuses}
    except Exception as exc:
        logger.error('[RISK] trigger-deps failed for user=%s: %s', current_user.id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
