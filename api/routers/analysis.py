# -*- coding: utf-8 -*-
"""
Analysis router - technical and fundamental analysis endpoints
"""
import json
import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from api.schemas.analysis import (
    TechnicalAnalysisResponse,
    FundamentalAnalysisResponse,
    TechReportListResponse,
    TechReportGenerateRequest,
    TechReportGenerateResponse,
    TechReportDetail,
)
from api.services import analysis_service
from api.services import rag_report_service

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/analysis', tags=['analysis'])


class ComprehensiveReportRequest(BaseModel):
    stock_code: str
    stock_name: str = ''
    report_type: str = 'comprehensive'


class OnePagerRequest(BaseModel):
    stock_code: str
    stock_name: str = ''


@router.get('/technical', response_model=TechnicalAnalysisResponse)
async def technical_analysis(
    code: str = Query(..., description="Stock code"),
):
    """Generate technical analysis report for a stock."""
    result = await analysis_service.get_technical_analysis(code)
    if not result.get('trade_date'):
        raise HTTPException(status_code=404, detail=f'No data found for stock {code}')
    return result


@router.get('/fundamental', response_model=FundamentalAnalysisResponse, deprecated=True)
async def fundamental_analysis(
    code: str = Query(..., description="Stock code"),
):
    """Generate fundamental analysis report for a stock.

    [DEPRECATED] Prefer POST /api/analysis/comprehensive/generate with
    report_type=fundamental for industry-aware FiveStepAnalyzer analysis.
    """
    result = await analysis_service.get_fundamental_analysis(code)
    return result


@router.get('/reports', response_model=TechReportListResponse)
async def list_reports(
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
):
    """List tech analysis reports, ordered by trade date desc."""
    return await analysis_service.list_tech_reports(limit=limit, offset=offset)


@router.post('/reports/generate', response_model=TechReportGenerateResponse)
async def generate_report(
    body: TechReportGenerateRequest,
):
    """Generate (or retrieve cached) a tech analysis report for a stock."""
    return await analysis_service.get_or_generate_tech_report(
        stock_code=body.stock_code,
        stock_name=body.stock_name or '',
    )


@router.get('/reports/by-stock', response_model=list[TechReportDetail])
async def get_reports_by_stock(
    code: str = Query(..., description="Stock code"),
    days: int = Query(3, ge=1, le=30, description="Number of recent calendar days"),
):
    """Get recent tech reports for a specific stock (last N days)."""
    return await analysis_service.get_stock_recent_reports(stock_code=code, days=days)


@router.get('/analyzed-stocks')
async def list_analyzed_stocks():
    """
    Return the most recent tech report per stock, joined with market cap and industry.
    Used for the stock card grid on the home view.
    """
    return await analysis_service.list_analyzed_stocks()


@router.get('/industry-tree')
async def list_industry_tree():
    """Return SW level-1 industry list with stock counts."""
    return await analysis_service.list_industry_tree()


@router.get('/reports/{code}/{trade_date}', response_model=TechReportDetail)
async def get_report_detail(
    code: str,
    trade_date: str,
):
    """Get full tech report detail including signals and indicators."""
    return await analysis_service.get_tech_report_detail(
        stock_code=code,
        trade_date_str=trade_date,
    )


@router.get('/report-html/{report_id}', response_class=HTMLResponse)
async def get_report_html(report_id: int):
    """Return the full HTML report content for embedding in an iframe."""
    html = await analysis_service.get_tech_report_html(report_id)
    if html is None:
        raise HTTPException(status_code=404, detail=f'Report {report_id} not found')
    if not html:
        raise HTTPException(status_code=404, detail='HTML report not available for this record (generated before v2)')
    return HTMLResponse(content=html)


# ---------------------------------------------------------------------------
# Five-section HTML report endpoints
# ---------------------------------------------------------------------------


class FiveSectionGenerateRequest(BaseModel):
    stock_code: str
    stock_name: str = ''


@router.get('/five-section/today')
async def get_today_five_section(
    code: str = Query(..., description='Stock code'),
):
    """Return today cached five-section report, or null if not generated."""
    report = rag_report_service.get_today_report(code, 'five_section')
    if report is None:
        return {'exists': False, 'report': None}
    return {'exists': True, 'report': {
        'id': report['id'],
        'stock_code': report['stock_code'],
        'stock_name': report['stock_name'],
        'report_date': report['report_date'],
        'created_at': report['created_at'],
    }}


@router.post('/five-section/generate')
async def generate_five_section(body: FiveSectionGenerateRequest):
    """
    Generate a five-section (technical/fund-flow/fundamental/sentiment/capital-cycle)
    HTML report. Synchronous - takes 10-30s depending on data availability.
    Returns report metadata (use /rag-report-html/{id} to view the HTML).
    """
    stock_code = body.stock_code
    stock_name = body.stock_name or stock_code

    # Check cache
    cached = rag_report_service.get_today_report(stock_code, 'five_section')
    if cached:
        return {
            'generated': False,
            'report_id': cached['id'],
            'report_date': cached['report_date'],
        }

    try:
        from data_analyst.research_pipeline.batch_runner import (
            build_report_data, _fmt_code, _bare_code,
        )
        from data_analyst.research_pipeline.renderer import FiveSectionRenderer
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=f'Module unavailable: {exc}')

    from datetime import date as _date
    date_str = _date.today().strftime('%Y%m%d')

    # Normalize code: strip .SH/.SZ suffix for batch_runner
    bare_code = stock_code.split('.')[0] if '.' in stock_code else stock_code

    try:
        report_data = build_report_data(bare_code, stock_name, date_str)
    except Exception as exc:
        logger.error('[five-section] build_report_data error: %s', exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f'Data collection failed: {exc}')

    if report_data is None:
        raise HTTPException(status_code=404, detail=f'Cannot build report data for {stock_code}')

    renderer = FiveSectionRenderer()
    html = renderer.render(report_data)

    try:
        report_id = rag_report_service.save_report(
            stock_code=stock_code,
            stock_name=stock_name,
            report_type='five_section',
            content=html,
        )
    except Exception as exc:
        logger.error('[five-section] save_report error: %s', exc)
        raise HTTPException(status_code=500, detail=f'Failed to save report: {exc}')

    return {
        'generated': True,
        'report_id': report_id,
        'report_date': _date.today().isoformat(),
        'composite_score': round(report_data.composite_score, 1),
        'direction': report_data.direction,
    }


@router.get('/rag-report-html/{report_id}', response_class=HTMLResponse)
async def get_rag_report_html(report_id: int):
    """Serve HTML content from trade_rag_report (five-section reports)."""
    content = rag_report_service.get_report_content(report_id)
    if content is None:
        raise HTTPException(status_code=404, detail=f'Report {report_id} not found')
    return HTMLResponse(content=content)


@router.get('/rag-report/{report_id}')
async def get_rag_report(report_id: int):
    """Return raw report content as JSON (for Markdown reports like one-pager)."""
    content = rag_report_service.get_report_content(report_id)
    if content is None:
        raise HTTPException(status_code=404, detail=f'Report {report_id} not found')
    return {'id': report_id, 'content': content}


# ---------------------------------------------------------------------------
# Comprehensive report (five-step RAG) endpoints
# ---------------------------------------------------------------------------

@router.get('/comprehensive/today')
async def get_today_comprehensive(
    code: str = Query(..., description='Stock code'),
    report_type: str = Query('comprehensive', description='Report type'),
):
    """Return today cached comprehensive report, or null if not generated."""
    report = rag_report_service.get_today_report(code, report_type)
    if report is None:
        return {'exists': False, 'report': None}
    return {'exists': True, 'report': report}


@router.post('/comprehensive/generate')
async def generate_comprehensive(body: ComprehensiveReportRequest):
    """
    SSE streaming endpoint to generate comprehensive report.
    Streams step-by-step progress; saves to DB on completion.

    SSE event types:
      {type: "cached",      report: {...}}        - already generated today
      {type: "plan",        sections: [...]}
      {type: "step_start",  step: "step1", name: "..."}
      {type: "step_done",   step: "step1", name: "...", content: "..."}
      {type: "done",        report_id: int, content: "..."}
      {type: "error",       message: "..."}
    """
    stock_code = body.stock_code
    stock_name = body.stock_name or stock_code
    report_type = body.report_type

    async def event_generator():
        # Check cache first
        cached = rag_report_service.get_today_report(stock_code, report_type)
        if cached:
            yield f"data: {json.dumps({'type': 'cached', 'report': cached}, ensure_ascii=False)}\n\n"
            return

        try:
            from investment_rag.report_engine.five_step import FiveStepAnalyzer
            from investment_rag.report_engine.report_builder import ReportBuilder
            from investment_rag.report_engine.prompts import FIVE_STEP_CONFIG
        except ImportError as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Module unavailable: {exc}'})}\n\n"
            return

        # Plan
        sections = []
        if report_type in ('fundamental', 'comprehensive'):
            sections.extend([c.name for c in FIVE_STEP_CONFIG])
        if report_type in ('technical', 'comprehensive'):
            sections.append('技术面')

        yield f"data: {json.dumps({'type': 'plan', 'sections': sections}, ensure_ascii=False)}\n\n"

        try:
            analyzer = FiveStepAnalyzer(db_env='online')
        except ValueError as exc:
            if 'RAG_API_KEY' in str(exc):
                yield f"data: {json.dumps({'type': 'error', 'message': 'RAG_API_KEY 未配置，请联系管理员配置 DashScope API Key'}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'message': f'配置错误: {exc}'}, ensure_ascii=False)}\n\n"
            return
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': f'初始化失败: {exc}'}, ensure_ascii=False)}\n\n"
            return
        builder = ReportBuilder()
        fundamental_results = {}
        tech_section = ''
        executive_summary = ''

        # Fundamental steps
        if report_type in ('fundamental', 'comprehensive'):
            step_outputs = {}
            for step_config in FIVE_STEP_CONFIG:
                yield f"data: {json.dumps({'type': 'step_start', 'step': step_config.step_id, 'name': step_config.name}, ensure_ascii=False)}\n\n"

                prev_summary = analyzer._build_prev_summary(step_config.step_id, step_outputs)
                step_result = analyzer._run_single_step(
                    step_config=step_config,
                    stock_code=stock_code,
                    stock_name=stock_name,
                    prev_analysis=prev_summary,
                    collection=None,
                )
                fundamental_results[step_config.step_id] = step_result
                step_outputs[step_config.step_id] = step_result

                yield f"data: {json.dumps({'type': 'step_done', 'step': step_config.step_id, 'name': step_config.name, 'content': step_result}, ensure_ascii=False)}\n\n"

            full_report_text = '\n\n---\n\n'.join(
                fundamental_results.get(sc.step_id, '') for sc in FIVE_STEP_CONFIG
            )
            executive_summary = analyzer._generate_executive_summary(
                stock_code=stock_code,
                stock_name=stock_name,
                full_analysis=full_report_text,
                system_prompt='',
            )

        # Technical section
        if report_type in ('technical', 'comprehensive'):
            yield f"data: {json.dumps({'type': 'step_start', 'step': 'tech', 'name': '技术面'}, ensure_ascii=False)}\n\n"
            tech_section = analyzer.generate_tech_section(stock_code, stock_name)
            yield f"data: {json.dumps({'type': 'step_done', 'step': 'tech', 'name': '技术面', 'content': tech_section}, ensure_ascii=False)}\n\n"

        # Assemble final report
        if report_type == 'comprehensive':
            final_report = builder.build_comprehensive(
                stock_code=stock_code,
                stock_name=stock_name,
                fundamental_results=fundamental_results,
                tech_section=tech_section,
                executive_summary=executive_summary,
            )
        elif report_type == 'fundamental':
            final_report = builder.build_fundamental_only(
                stock_code=stock_code,
                stock_name=stock_name,
                fundamental_results=fundamental_results,
                executive_summary=executive_summary,
            )
        else:
            final_report = f"# {stock_name}({stock_code}) 技术面分析\n\n{tech_section}"

        # Save to DB
        try:
            report_id = rag_report_service.save_report(
                stock_code=stock_code,
                stock_name=stock_name,
                report_type=report_type,
                content=final_report,
            )
        except Exception as exc:
            logger.error('[comprehensive] save_report error: %s', exc)
            report_id = 0

        yield f"data: {json.dumps({'type': 'done', 'report_id': report_id, 'content': final_report}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )


# ---------------------------------------------------------------------------
# One-pager report endpoints
# ---------------------------------------------------------------------------

@router.get('/one-pager/today')
async def get_today_one_pager(
    code: str = Query(..., description='Stock code'),
):
    """Return today cached one-pager report, or null if not generated."""
    report = rag_report_service.get_today_report(code, 'one_pager')
    if report is None:
        return {'exists': False, 'report': None}
    return {'exists': True, 'report': report}


@router.get('/one-pager/history')
async def list_one_pager_history(
    code: str = Query(..., description='Stock code'),
    limit: int = Query(10, ge=1, le=50, description='Max results'),
):
    """Return historical one-pager reports for a stock."""
    sql = """
        SELECT id, stock_code, stock_name, report_type, report_date, created_at
        FROM trade_rag_report
        WHERE stock_code = %s AND report_type = 'one_pager'
        ORDER BY report_date DESC, created_at DESC
        LIMIT %s
    """
    from config.db import execute_query
    rows = list(execute_query(sql, (code, limit)))
    return [
        {
            'id': r['id'],
            'stock_code': r['stock_code'],
            'stock_name': r['stock_name'],
            'report_type': r['report_type'],
            'report_date': str(r['report_date']),
            'created_at': str(r['created_at']),
        }
        for r in rows
    ]


@router.post('/one-pager/generate')
async def generate_one_pager(body: OnePagerRequest):
    """
    SSE streaming endpoint to generate one-pager deep research report.
    Streams step-by-step progress (part1: A-E, part2: F-I); saves to DB on completion.

    SSE event types:
      {type: "cached",     report: {...}}
      {type: "plan",       sections: [...]}
      {type: "step_start", step: "part1", name: "..."}
      {type: "step_done",  step: "part1", name: "...", content: "..."}
      {type: "done",       report_id: int, content: "..."}
      {type: "error",      message: "..."}
    """
    stock_code = body.stock_code
    stock_name = body.stock_name or stock_code

    async def event_generator():
        # Check cache
        cached = rag_report_service.get_today_report(stock_code, 'one_pager')
        if cached:
            yield f"data: {json.dumps({'type': 'cached', 'report': cached}, ensure_ascii=False)}\n\n"
            return

        try:
            from investment_rag.report_engine.one_pager import OnePagerAnalyzer
        except ImportError as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Module unavailable: {exc}'})}\n\n"
            return

        sections = ['数据采集', '上半页 (A-E)', '下半页 (F-I)']
        yield f"data: {json.dumps({'type': 'plan', 'sections': sections}, ensure_ascii=False)}\n\n"

        try:
            analyzer = OnePagerAnalyzer(db_env='online')
        except ValueError as exc:
            if 'RAG_API_KEY' in str(exc):
                yield f"data: {json.dumps({'type': 'error', 'message': 'RAG_API_KEY 未配置，请联系管理员配置 DashScope API Key'}, ensure_ascii=False)}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'error', 'message': f'配置错误: {exc}'}, ensure_ascii=False)}\n\n"
            return
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': f'初始化失败: {exc}'}, ensure_ascii=False)}\n\n"
            return

            # Data collection step
            yield f"data: {json.dumps({'type': 'step_start', 'step': 'data', 'name': '数据采集'}, ensure_ascii=False)}\n\n"
            data_blocks = analyzer._data_collector.collect(stock_code, stock_name)
            rag_context = analyzer._fetch_rag_context(stock_code, stock_name, 'reports')
            data_blocks['rag_context'] = rag_context
            yield f"data: {json.dumps({'type': 'step_done', 'step': 'data', 'name': '数据采集', 'content': '已采集13个数据块'}, ensure_ascii=False)}\n\n"

            # LLM generation steps
            from investment_rag.report_engine.prompts import ONE_PAGER_STEPS, ONE_PAGER_SYSTEM_PROMPT
            from datetime import date as _date

            today = _date.today()
            system_prompt = ONE_PAGER_SYSTEM_PROMPT.format(today=today.isoformat())
            results = {}

            for step_config in ONE_PAGER_STEPS:
                sid = step_config.step_id
                sname = step_config.name

                yield f"data: {json.dumps({'type': 'step_start', 'step': sid, 'name': sname}, ensure_ascii=False)}\n\n"

                prompt = analyzer._build_prompt(
                    step_config=step_config,
                    stock_code=stock_code,
                    stock_name=stock_name,
                    data_blocks=data_blocks,
                    part1_result=results.get('part1', ''),
                )

                try:
                    content = analyzer._llm.generate(
                        prompt=prompt,
                        system_prompt=system_prompt,
                        temperature=0.4,
                        max_tokens=3000,
                    )
                except Exception as e:
                    content = f"[{sname}] LLM 调用失败: {e}"

                results[sid] = content
                yield f"data: {json.dumps({'type': 'step_done', 'step': sid, 'name': sname, 'content': content}, ensure_ascii=False)}\n\n"

            # Assemble
            price_str = analyzer._extract_price(data_blocks.get('valuation_snapshot', ''))
            header = (
                f"# {stock_name} | 一页纸深度研究\n\n"
                f"**市场**：A股  **股票代码**：{stock_code}  "
                f"**分析日期**：{today.isoformat()}  **价格**：{price_str}（最新收盘）"
            )
            final_report = header + "\n\n" + results.get('part1', '') + "\n\n---\n\n" + results.get('part2', '')

            # Save to DB
            try:
                report_id = rag_report_service.save_report(
                    stock_code=stock_code,
                    stock_name=stock_name,
                    report_type='one_pager',
                    content=final_report,
                )
            except Exception as exc:
                logger.error('[one-pager] save_report error: %s', exc)
                report_id = 0

            yield f"data: {json.dumps({'type': 'done', 'report_id': report_id, 'content': final_report}, ensure_ascii=False)}\n\n"

        except Exception as exc:
            logger.error('[one-pager] generation error: %s', exc, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )


# ---------------------------------------------------------------------------
# Data Health Check endpoints
# ---------------------------------------------------------------------------

@router.get('/health-check/latest')
async def get_latest_health_check():
    """Get latest data health check results."""
    try:
        from scheduler.check_data_completeness import get_latest_health
        results = get_latest_health()
        return {'check_time': results[0]['check_time'] if results else None, 'results': results}
    except Exception as exc:
        logger.error('[health-check] get_latest failed: %s', exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get('/health-check/summary')
async def get_health_summary():
    """Get data health summary (counts by status)."""
    try:
        from scheduler.check_data_completeness import get_health_summary
        return get_health_summary()
    except Exception as exc:
        logger.error('[health-check] summary failed: %s', exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post('/health-check/run')
async def run_health_check():
    """Manually trigger a health check."""
    try:
        from scheduler.check_data_completeness import run_check
        result = run_check()
        return result
    except Exception as exc:
        logger.error('[health-check] run failed: %s', exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Unified async report task endpoints
# ---------------------------------------------------------------------------

VALID_REPORT_TYPES = frozenset({
    'one_pager', 'comprehensive', 'fundamental', 'five_section', 'technical_report',
})


class ReportSubmitRequest(BaseModel):
    stock_code: str
    stock_name: str = ''
    report_type: str = 'comprehensive'


@router.post('/report/submit')
async def submit_report(body: ReportSubmitRequest):
    """
    Submit a report generation job to Celery.

    report_type: one_pager | comprehensive | fundamental | five_section | technical_report

    Returns immediately with one of:
      {status: "cached",    report_id, report_type}
      {status: "pending"|"running", task_id}
      {status: "submitted", task_id, message}
    """
    stock_code = body.stock_code
    stock_name = body.stock_name or stock_code
    report_type = body.report_type

    if report_type not in VALID_REPORT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f'Invalid report_type. Valid values: {sorted(VALID_REPORT_TYPES)}',
        )

    from api.services import report_task_service
    from api.services import rag_report_service

    # 1. Check today's cache in trade_rag_report
    cached = rag_report_service.get_today_report(stock_code, report_type)
    if cached:
        return {
            'status': 'cached',
            'report_id': cached['id'],
            'report_type': report_type,
            'stock_code': stock_code,
        }

    # 2. Check for an in-flight task
    latest = report_task_service.get_latest_task(stock_code, report_type)
    if latest and latest['status'] in ('pending', 'running'):
        return {
            'status': latest['status'],
            'task_id': latest['task_id'],
            'report_type': report_type,
            'stock_code': stock_code,
        }

    # 3. Submit new Celery task
    try:
        from api.tasks.report_tasks import generate_report_task
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=f'Task module unavailable: {exc}')

    import uuid
    task_id = str(uuid.uuid4())

    generate_report_task.apply_async(
        args=[task_id, stock_code, stock_name, report_type],
        task_id=task_id,
    )

    # 4. Persist task row
    report_task_service.create_task(
        task_id=task_id,
        stock_code=stock_code,
        stock_name=stock_name,
        report_type=report_type,
    )

    logger.info('[report/submit] submitted task_id=%s stock=%s type=%s', task_id, stock_code, report_type)
    return {
        'status': 'submitted',
        'task_id': task_id,
        'report_type': report_type,
        'stock_code': stock_code,
        'message': '报告生成中，请稍后刷新查看',
    }


@router.get('/report/status')
async def get_report_status(task_id: str = Query(..., description='Celery task UUID')):
    """
    Poll the status of a submitted report task.

    Returns task row: {task_id, status, report_id, error_msg, report_type, stock_code}
    """
    from api.services import report_task_service

    task = report_task_service.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f'Task {task_id} not found')
    return task


@router.get('/report/latest')
async def get_latest_report(
    code: str = Query(..., description='Stock code'),
    report_type: str = Query('comprehensive', description='Report type'),
):
    """
    Return the latest report info for a stock+type combination.

    Checks trade_rag_report cache first, then trade_report_task.
    Returns: {cached: bool, report_id?, task_id?, status?, report_type}
    """
    if report_type not in VALID_REPORT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f'Invalid report_type. Valid values: {sorted(VALID_REPORT_TYPES)}',
        )

    from api.services import report_task_service
    from api.services import rag_report_service

    # 1. Check today's cache
    cached = rag_report_service.get_today_report(code, report_type)
    if cached:
        return {
            'cached': True,
            'report_id': cached['id'],
            'report_type': report_type,
            'stock_code': code,
            'report_date': cached['report_date'],
        }

    # 2. Check latest task
    latest = report_task_service.get_latest_task(code, report_type)
    if latest:
        return {
            'cached': False,
            'task_id': latest['task_id'],
            'status': latest['status'],
            'report_id': latest.get('report_id'),
            'report_type': report_type,
            'stock_code': code,
        }

    return {
        'cached': False,
        'report_type': report_type,
        'stock_code': code,
        'status': None,
    }


# ---------------------------------------------------------------------------
# Annual Report Ingest Endpoints
# ---------------------------------------------------------------------------

class IngestTriggerRequest(BaseModel):
    stock_code: str
    stock_name: str
    years: int = 3


@router.post('/annual-report/ingest')
async def trigger_annual_report_ingest(body: IngestTriggerRequest):
    """
    Trigger background ingestion of annual report PDFs into ChromaDB.
    Idempotent: skips years already ingested.
    Returns immediately; processing happens in Celery worker.
    """
    from api.tasks.ingest_tasks import ingest_annual_reports_task

    bare = body.stock_code.split('.')[0] if '.' in body.stock_code else body.stock_code
    task = ingest_annual_reports_task.delay(
        stock_code=bare,
        stock_name=body.stock_name,
        years=body.years,
    )
    logger.info(
        '[api] ingest_annual_reports triggered: stock=%s task_id=%s',
        bare, task.id,
    )
    return {
        'task_id': task.id,
        'stock_code': bare,
        'stock_name': body.stock_name,
        'years': body.years,
        'message': 'Annual report ingest started in background',
    }


@router.get('/annual-report/status')
async def get_annual_report_ingest_status(code: str = Query(..., description='6-digit stock code')):
    """Check how many annual report chunks are in ChromaDB for a stock."""
    try:
        from investment_rag.config import load_config
        from investment_rag.store.chroma_client import ChromaClient

        cfg = load_config()
        client = ChromaClient(config=cfg)
        col = client.get_collection('annual_reports')
        results = col.get(
            where={"stock_code": {"$eq": code}},
            limit=1000,
        )
        ids = results.get('ids', [])
        metadatas = results.get('metadatas', [])
        years = sorted({m.get('report_year', '') for m in (metadatas or []) if m.get('report_year')}, reverse=True)
        return {
            'stock_code': code,
            'total_chunks': len(ids),
            'years_available': years,
            'has_data': len(ids) > 0,
        }
    except Exception as e:
        logger.error('[api] annual-report status error: %s', e)
        return {'stock_code': code, 'total_chunks': 0, 'years_available': [], 'has_data': False}


# ---------------------------------------------------------------------------
# 估值分位 API
# ---------------------------------------------------------------------------

@router.get('/valuation/temperature')
async def industry_valuation_temperature(
    date: str = Query(None, description='交易日 YYYY-MM-DD，不传则取最新'),
):
    """
    获取申万一级行业估值温度。

    返回各行业的 PE/PB 及历史分位，按 valuation_score 升序排列（低估在前）。
    valuation_score 范围 0-100，越低估值越低。
    valuation_label: 低估 / 合理 / 高估
    """
    return await analysis_service.get_industry_valuation_temperature(trade_date=date)


@router.get('/valuation/industry/{industry_name}/history')
async def industry_valuation_history(
    industry_name: str,
    metric: str = Query('pe_ttm', description='指标: pe_ttm | pe_ttm_eq | pe_ttm_med | pb | pb_med'),
    years: int = Query(5, description='历史年数: 5 或 10'),
):
    """
    获取指定申万行业的估值历史走势及分位带。

    返回历史时序数据（每日一条）及 p20/p50/p80 分位参考线。
    """
    return await analysis_service.get_industry_valuation_history(industry_name, metric=metric, years=years)


@router.get('/valuation/stock/{code}/history')
async def stock_valuation_history(
    code: str,
    years: int = Query(5, description='历史年数: 5 或 10'),
):
    """
    获取个股历史 PE/PB 走势 + 分位带。

    返回历史 PE-TTM / PB 时序及当前估值在历史中的分位位置。
    """
    return await analysis_service.get_stock_valuation_history(code, years=years)


# ---------------------------------------------------------------------------
# Stock News & Dynamics
# ---------------------------------------------------------------------------

@router.get('/stock-news')
async def get_stock_news(
    code: str = Query(..., description="Stock code, e.g. 601872.SH or 601872"),
    days: int = Query(7, ge=1, le=30, description="Lookback days"),
):
    """Get recent news for a stock with event detection tags."""
    from api.services.stock_news_service import get_stock_news_list
    return await get_stock_news_list(code, days=days)


@router.get('/stock-news/analysis')
async def get_stock_news_analysis(
    code: str = Query(..., description="Stock code"),
    name: str = Query('', description="Stock name for LLM context"),
):
    """Get LLM-generated news sentiment analysis for a stock (cached daily)."""
    from api.services.stock_news_service import analyze_stock_news
    return await analyze_stock_news(code, stock_name=name)
