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


@router.get('/fundamental', response_model=FundamentalAnalysisResponse)
async def fundamental_analysis(
    code: str = Query(..., description="Stock code"),
):
    """Generate fundamental analysis report for a stock."""
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
    Return the most recent tech report per stock, joined with market cap.
    Used for the stock card grid on the home view.
    """
    return await analysis_service.list_analyzed_stocks()


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

        analyzer = FiveStepAnalyzer(db_env='online')
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
