# -*- coding: utf-8 -*-
"""
Celery task for unified report generation.
Handles: one_pager, comprehensive, fundamental, five_section, technical_report
"""
import logging
import traceback

from api.tasks.celery_app import celery_app

logger = logging.getLogger('myTrader.tasks')

# Ensure table exists at import time (lazy, cached after first call)
try:
    from api.services import report_task_service as _rts
    _rts.ensure_table()
except Exception as _e:
    logger.warning('[report_tasks] ensure_table at import failed: %s', _e)


@celery_app.task(bind=True, name='tasks.generate_report')
def generate_report_task(
    self,
    task_id: str,
    stock_code: str,
    stock_name: str,
    report_type: str,
):
    """
    Generate a report of the given type and persist it to trade_rag_report.

    Args:
        task_id:     Celery task UUID (also stored in trade_report_task)
        stock_code:  Stock code (may include .SH/.SZ suffix)
        stock_name:  Stock display name
        report_type: one_pager | comprehensive | fundamental | five_section | technical_report
    """
    logger.info(
        '[CELERY] generate_report_task start: task_id=%s stock=%s type=%s',
        task_id, stock_code, report_type,
    )

    # Import here to avoid circular imports
    from api.services import report_task_service
    from api.services import rag_report_service

    report_task_service.update_task_running(task_id)

    try:
        content = _dispatch(report_type, stock_code, stock_name)

        report_id = rag_report_service.save_report(
            stock_code=stock_code,
            stock_name=stock_name,
            report_type=report_type,
            content=content,
        )

        report_task_service.update_task_done(task_id, report_id)
        logger.info(
            '[CELERY] generate_report_task done: task_id=%s report_id=%d',
            task_id, report_id,
        )
        return {'task_id': task_id, 'report_id': report_id, 'status': 'done'}

    except Exception as exc:
        error_msg = f'{str(exc)[:500]}\n{traceback.format_exc()}'
        logger.error(
            '[CELERY] generate_report_task failed: task_id=%s error=%s',
            task_id, error_msg,
        )
        try:
            report_task_service.update_task_failed(task_id, error_msg)
        except Exception as update_exc:
            logger.error(
                '[CELERY] Failed to write task failure status: task_id=%s err=%s',
                task_id, update_exc,
            )
        self.update_state(state='FAILURE', meta={'error': str(exc)[:500]})
        raise


# ---------------------------------------------------------------------------
# Internal dispatch helpers
# ---------------------------------------------------------------------------

def _ensure_financial_data(stock_code: str, stock_name: str) -> None:
    """Ensure financial_cashflow has recent data for this stock; sync if missing."""
    try:
        import os
        import sys
        ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if ROOT not in sys.path:
            sys.path.insert(0, ROOT)

        from config.db import execute_query
        bare = stock_code.split('.')[0] if '.' in stock_code else stock_code

        # Check if we have data within last 18 months (covers latest annual report)
        from datetime import date, timedelta
        cutoff = (date.today() - timedelta(days=548)).strftime('%Y-%m-%d')
        rows = execute_query(
            "SELECT COUNT(*) AS cnt FROM financial_cashflow WHERE stock_code=%s AND report_date >= %s",
            (bare, cutoff), env='online',
        )
        if rows and rows[0]['cnt'] > 0:
            return  # already have recent data

        logger.info('[report_tasks] syncing cashflow for %s', bare)
        from data_analyst.financial_fetcher.fetcher import fetch_cashflow
        from data_analyst.financial_fetcher.storage import FinancialStorage
        cashflow_rows = fetch_cashflow(bare, stock_name)
        if cashflow_rows:
            FinancialStorage(env='online').upsert('financial_cashflow', cashflow_rows)
            logger.info('[report_tasks] synced %d cashflow rows for %s', len(cashflow_rows), bare)
    except Exception as e:
        logger.warning('[report_tasks] _ensure_financial_data failed for %s: %s', stock_code, e)


def _dispatch(report_type: str, stock_code: str, stock_name: str) -> str:
    if report_type == 'one_pager':
        _ensure_financial_data(stock_code, stock_name)
        return _generate_one_pager(stock_code, stock_name)
    if report_type in ('comprehensive', 'fundamental'):
        return _generate_comprehensive(report_type, stock_code, stock_name)
    if report_type == 'five_section':
        return _generate_five_section(stock_code, stock_name)
    if report_type == 'technical_report':
        return _generate_technical_report(stock_code, stock_name)
    raise ValueError(f'Unknown report_type: {report_type}')


def _generate_one_pager(stock_code: str, stock_name: str) -> str:
    import os
    import sys

    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    from investment_rag.report_engine.one_pager import OnePagerAnalyzer

    analyzer = OnePagerAnalyzer(db_env='online')
    results = analyzer.generate(
        stock_code=stock_code,
        stock_name=stock_name,
        collection='reports',
    )
    return results.get('full_report', '')


def _generate_comprehensive(report_type: str, stock_code: str, stock_name: str) -> str:
    import os
    import sys

    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    from investment_rag.report_engine.five_step import FiveStepAnalyzer
    from investment_rag.report_engine.report_builder import ReportBuilder

    analyzer = FiveStepAnalyzer(db_env='online')
    builder = ReportBuilder()

    fundamental_results = analyzer.generate_fundamental(
        stock_code=stock_code,
        stock_name=stock_name,
    )

    tech_section = ''
    if report_type == 'comprehensive':
        tech_section = analyzer.generate_tech_section(stock_code, stock_name)

    executive_summary = fundamental_results.get('executive_summary', '')

    step_results = {
        k: v for k, v in fundamental_results.items()
        if k.startswith('step')
    }

    if report_type == 'comprehensive':
        return builder.build_comprehensive(
            stock_code=stock_code,
            stock_name=stock_name,
            fundamental_results=step_results,
            tech_section=tech_section,
            executive_summary=executive_summary,
        )
    else:
        return builder.build_fundamental_only(
            stock_code=stock_code,
            stock_name=stock_name,
            fundamental_results=step_results,
            executive_summary=executive_summary,
        )


def _generate_five_section(stock_code: str, stock_name: str) -> str:
    import os
    import sys
    from datetime import date as _date

    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    from data_analyst.research_pipeline.batch_runner import build_report_data
    from data_analyst.research_pipeline.renderer import FiveSectionRenderer

    date_str = _date.today().strftime('%Y%m%d')
    bare_code = stock_code.split('.')[0] if '.' in stock_code else stock_code

    report_data = build_report_data(bare_code, stock_name, date_str)
    if report_data is None:
        raise ValueError(f'Cannot build five_section report data for {stock_code}')

    renderer = FiveSectionRenderer()
    return renderer.render(report_data)


def _generate_technical_report(stock_code: str, stock_name: str) -> str:
    import asyncio

    from api.services.analysis_service import get_or_generate_tech_report

    # Celery worker threads may not have an event loop; create one if needed
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError('closed')
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    result = loop.run_until_complete(
        get_or_generate_tech_report(stock_code=stock_code, stock_name=stock_name)
    )
    # get_or_generate_tech_report returns a dict; we serialize the key fields as text
    import json
    return json.dumps(result, ensure_ascii=False, default=str)
