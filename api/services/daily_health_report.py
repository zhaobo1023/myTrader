# -*- coding: utf-8 -*-
"""
Daily Data Health Report -- push data completeness and task execution
status to Feishu bot.

Reuses the same data sources as the /data-health frontend page:
- admin.get_data_health() for table freshness & completeness
- trade_task_run_log for task execution results

Focuses on actionable alerts: failed tasks, stale data, missing outputs.
"""
import json
import logging
from datetime import date

from config.db import execute_query

logger = logging.getLogger('myTrader.health_report')


# ---------------------------------------------------------------------------
# 1. Collect data health (same checks as admin.py /api/admin/data-health)
# ---------------------------------------------------------------------------

_HEALTH_CHECKS = [
    # (key, label, group, sql_date, warn_days)
    ('daily_price', 'A股日线', '行情', "SELECT MAX(trade_date) as d FROM trade_stock_daily", 1),
    ('etf_daily', 'ETF日线', '行情', "SELECT MAX(trade_date) as d FROM trade_etf_daily", 1),
    ('basic_factor', '基础因子', '因子', "SELECT MAX(calc_date) as d FROM trade_stock_basic_factor", 2),
    ('rps', 'RPS排名', '因子', "SELECT MAX(trade_date) as d FROM trade_stock_rps", 2),
    ('log_bias', 'LogBias', '因子', "SELECT MAX(trade_date) as d FROM trade_log_bias_daily", 1),
    ('fear_index', '恐贪指数', '情绪', "SELECT MAX(trade_date) as d FROM trade_fear_index", 3),
    ('limit_detail', '涨跌停明细', '情绪', "SELECT MAX(trade_date) as d FROM trade_limit_stock_detail", 1),
    ('macro', '宏观指标', '宏观', "SELECT MAX(date) as d FROM macro_data WHERE indicator = 'gold'", 3),
    ('briefing', '晨报/复盘', '输出', "SELECT MAX(brief_date) as d FROM trade_briefing", 1),
    ('moneyflow', '资金流向', '补充', "SELECT MAX(trade_date) as d FROM trade_stock_moneyflow", 2),
    ('margin', '融资融券', '补充', "SELECT MAX(trade_date) as d FROM trade_margin_trade", 2),
    ('north', '北向持仓', '补充', "SELECT MAX(trade_date) as d FROM trade_north_holding", 2),
    ('theme_score', '主题池评分', '策略', "SELECT MAX(score_date) as d FROM theme_pool_scores", 2),
    ('concept_map', '概念板块', '策略', "SELECT MAX(trade_date) as d FROM stock_concept_map", 7),
]


def _collect_table_health(today: date) -> list[dict]:
    """Check freshness for each monitored table."""
    results = []
    for key, label, group, sql, warn_days in _HEALTH_CHECKS:
        try:
            rows = execute_query(sql, env='online')
            if not rows or not rows[0].get('d'):
                results.append({'key': key, 'label': label, 'group': group,
                                'status': 'error', 'lag': None, 'latest': None})
                continue

            d = rows[0]['d']
            if hasattr(d, 'date'):
                d = d.date()
            elif isinstance(d, str):
                from datetime import datetime as _dt
                d = _dt.strptime(str(d)[:10], '%Y-%m-%d').date()

            lag = (today - d).days
            if lag <= warn_days:
                status = 'ok'
            elif lag <= warn_days * 2:
                status = 'warn'
            else:
                status = 'error'

            results.append({'key': key, 'label': label, 'group': group,
                            'status': status, 'lag': lag, 'latest': str(d)})
        except Exception as e:
            # Table doesn't exist or other error -- skip silently
            results.append({'key': key, 'label': label, 'group': group,
                            'status': 'error', 'lag': None, 'latest': None,
                            'error': str(e)[:60]})
    return results


# ---------------------------------------------------------------------------
# 2. Collect task runs (from trade_task_run_log)
# ---------------------------------------------------------------------------

_TASK_LABELS = {
    'fetch_daily_price': 'A股日线拉取',
    'fetch_etf_daily': 'ETF日线拉取',
    'fetch_macro_data': '宏观指标拉取',
    'fetch_global_assets': '全球资产拉取',
    'fetch_dashboard': '市场看板指标',
    'calc_basic_factor': '基础量价因子',
    'calc_extended_factor': '扩展因子',
    'calc_rps': 'RPS相对强度',
    'calc_technical': '技术指标',
    'calc_log_bias': '对数偏差',
    'calc_svd_monitor': 'SVD市场状态',
    'run_universe_scan': '全市场扫描',
    'run_theme_score': '主题池评分',
    'monitor_candidate': '候选池监控',
    'briefing_morning': '早报',
    'briefing_evening': '晚报',
    'calc_dashboard_signal': '看板信号计算',
    'calc_fear_index': '恐慌指数',
}


def _collect_task_runs(target_date: date) -> dict:
    """Get task execution results for the target date."""
    try:
        rows = execute_query(
            """SELECT task_name, task_group, status, duration_ms,
                      record_count, error_msg
               FROM trade_task_run_log
               WHERE run_date = %s
               ORDER BY task_group, task_name""",
            (str(target_date),),
            env='online',
        )
    except Exception as e:
        logger.warning('trade_task_run_log query failed: %s', e)
        return {'available': False, 'error': str(e)}

    total = len(rows)
    success = sum(1 for r in rows if r['status'] == 'success')
    failed = sum(1 for r in rows if r['status'] == 'failed')
    running = sum(1 for r in rows if r['status'] == 'running')
    skipped = sum(1 for r in rows if r['status'] == 'skipped')

    failed_tasks = []
    for r in rows:
        if r['status'] == 'failed':
            failed_tasks.append({
                'name': _TASK_LABELS.get(r['task_name'], r['task_name']),
                'task_id': r['task_name'],
                'group': r.get('task_group', ''),
                'error': (r.get('error_msg') or '')[:80],
            })

    # Tasks still in 'running' status = probably hung
    hung_tasks = []
    for r in rows:
        if r['status'] == 'running':
            hung_tasks.append({
                'name': _TASK_LABELS.get(r['task_name'], r['task_name']),
                'task_id': r['task_name'],
            })

    slow_tasks = []
    for r in rows:
        dur = r.get('duration_ms') or 0
        if r['status'] == 'success' and dur > 300000:  # > 5 min
            slow_tasks.append({
                'name': _TASK_LABELS.get(r['task_name'], r['task_name']),
                'duration_s': round(dur / 1000),
            })

    return {
        'available': True,
        'total': total,
        'success': success,
        'failed': failed,
        'running': running,
        'skipped': skipped,
        'failed_tasks': failed_tasks,
        'hung_tasks': hung_tasks,
        'slow_tasks': slow_tasks,
    }


# ---------------------------------------------------------------------------
# 3. Build & push report
# ---------------------------------------------------------------------------

def build_health_report(target_date: date = None) -> dict:
    """Build daily health report from data checks and task runs."""
    if target_date is None:
        target_date = date.today()

    table_health = _collect_table_health(target_date)
    task_runs = _collect_task_runs(target_date)

    # Overall stats
    ok_count = sum(1 for t in table_health if t['status'] == 'ok')
    warn_count = sum(1 for t in table_health if t['status'] == 'warn')
    error_count = sum(1 for t in table_health if t['status'] == 'error')
    total_tables = len(table_health)
    failed_task_count = task_runs.get('failed', 0)
    hung_task_count = len(task_runs.get('hung_tasks', []))

    # Determine level
    if error_count > 2 or failed_task_count > 2 or hung_task_count > 0:
        level = 'critical'
    elif warn_count > 2 or failed_task_count > 0 or error_count > 0:
        level = 'warn'
    else:
        level = 'ok'

    # Summary line
    parts = ['数据 {}/{} 正常'.format(ok_count, total_tables)]
    if task_runs.get('available') and task_runs['total'] > 0:
        parts.append('任务 {}/{} 成功'.format(task_runs['success'], task_runs['total']))
    if failed_task_count:
        parts.append('{} 个失败'.format(failed_task_count))
    if hung_task_count:
        parts.append('{} 个卡住'.format(hung_task_count))
    summary = ' | '.join(parts)

    return {
        'date': str(target_date),
        'level': level,
        'summary': summary,
        'table_health': table_health,
        'task_runs': task_runs,
        'ok': ok_count,
        'warn': warn_count,
        'error': error_count,
        'total': total_tables,
    }


def push_health_report(target_date: date = None) -> dict:
    """Build health report and push to Feishu bot as a card."""
    import httpx
    from api.config import settings
    from api.services.feishu_doc_publisher import _headers, _OWNER_OPEN_ID

    report = build_health_report(target_date)
    health_url = getattr(settings, 'DATA_HEALTH_URL', '') or 'http://123.56.3.1/data-health'

    # -- Build card content --
    color_map = {'ok': 'green', 'warn': 'orange', 'critical': 'red'}
    level_text = {'ok': '正常', 'warn': '有警告', 'critical': '有异常'}

    # Card body lines (lark_md format)
    body_lines = []

    # 1. Failed tasks (most important)
    failed = report['task_runs'].get('failed_tasks', [])
    if failed:
        body_lines.append('**[FAIL] 失败任务:**')
        for ft in failed:
            body_lines.append('- {} | {}'.format(ft['name'], ft['error'] or '未知错误'))
        body_lines.append('')

    # 2. Hung tasks
    hung = report['task_runs'].get('hung_tasks', [])
    if hung:
        body_lines.append('**[HANG] 卡住任务(仍在running):**')
        for ht in hung:
            body_lines.append('- {}'.format(ht['name']))
        body_lines.append('')

    # 3. Data anomalies
    errors = [t for t in report['table_health'] if t['status'] == 'error']
    warns = [t for t in report['table_health'] if t['status'] == 'warn']

    if errors:
        body_lines.append('**[FAIL] 数据异常:**')
        for t in errors:
            if t.get('lag') is not None:
                body_lines.append('- {} 滞后{}天 (最新: {})'.format(
                    t['label'], t['lag'], t.get('latest', '-')))
            else:
                body_lines.append('- {} 无数据或表不存在'.format(t['label']))
        body_lines.append('')

    if warns:
        body_lines.append('**[WARN] 数据偏旧:**')
        for t in warns:
            body_lines.append('- {} 滞后{}天'.format(t['label'], t['lag']))
        body_lines.append('')

    # 4. Slow tasks
    slow = report['task_runs'].get('slow_tasks', [])
    if slow:
        body_lines.append('**慢任务(>5分钟):**')
        for st in slow:
            body_lines.append('- {} ({}秒)'.format(st['name'], st['duration_s']))
        body_lines.append('')

    # 5. If everything is fine
    if not body_lines:
        body_lines.append('所有数据正常产出，无异常任务')

    card = {
        'config': {'wide_screen_mode': True},
        'header': {
            'title': {'tag': 'plain_text',
                      'content': '数据健康日报 {} [{}]'.format(
                          report['date'],
                          level_text.get(report['level'], ''))},
            'template': color_map.get(report['level'], 'blue'),
        },
        'elements': [
            {
                'tag': 'div',
                'text': {'tag': 'lark_md', 'content': report['summary']},
            },
            {'tag': 'hr'},
            {
                'tag': 'div',
                'text': {'tag': 'lark_md', 'content': '\n'.join(body_lines)},
            },
            {'tag': 'hr'},
            {
                'tag': 'action',
                'actions': [{
                    'tag': 'button',
                    'text': {'tag': 'plain_text', 'content': '查看详情'},
                    'type': 'default',
                    'url': health_url,
                }],
            },
        ],
    }

    msg = {
        'receive_id': _OWNER_OPEN_ID,
        'msg_type': 'interactive',
        'content': json.dumps(card, ensure_ascii=False),
    }

    try:
        resp = httpx.post(
            'https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id',
            headers=_headers(),
            json=msg,
            timeout=15,
        )
        data = resp.json()
        if data.get('code') != 0:
            logger.warning('Health report push failed: %s', data.get('msg'))
            report['push_status'] = 'failed'
        else:
            logger.info('Health report pushed to Feishu')
            report['push_status'] = 'sent'
    except Exception as e:
        logger.warning('Failed to push health report: %s', e)
        report['push_status'] = 'error'

    return report
