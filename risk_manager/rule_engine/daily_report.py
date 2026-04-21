# -*- coding: utf-8 -*-
"""
风控日报生成 + 信箱推送

依赖: config.db, api.services.inbox_service (myTrader 项目)
"""
import logging
from datetime import datetime

from .scanner import scan_portfolio

logger = logging.getLogger('risk_manager.daily_report')


def generate_risk_report(user_id: int, env: str = 'online') -> str:
    """
    Generate a Markdown risk report for a user's portfolio.

    Returns:
        Markdown formatted report string.
    """
    scan = scan_portfolio(user_id, env=env)
    summary = scan['portfolio_summary']
    stock_alerts = scan['stock_alerts']
    portfolio_alerts = scan['portfolio_alerts']

    lines = []
    lines.append(f"# 持仓风控日报")
    lines.append(f"")
    lines.append(f"扫描时间: {scan['scan_time'][:19]}")
    lines.append(f"")

    # Portfolio summary
    lines.append(f"## 组合概览")
    lines.append(f"")
    lines.append(f"- 持仓数量: {summary['total_positions']}")
    if summary.get('total_value'):
        lines.append(f"- 持仓总市值: {summary['total_value']:,.0f}")
    if summary.get('l1_count') is not None:
        lines.append(f"- L1: {summary.get('l1_count', 0)}, L2: {summary.get('l2_count', 0)}")
    if summary.get('scan_date'):
        lines.append(f"- 数据日期: {summary['scan_date']}")
    lines.append(f"")

    # Portfolio-level alerts
    if portfolio_alerts:
        lines.append(f"## 组合风险提示")
        lines.append(f"")
        for alert in portfolio_alerts:
            lines.append(f"- {alert}")
        lines.append(f"")

    # Stock-level alerts
    if stock_alerts:
        lines.append(f"## 个股风险提示")
        lines.append(f"")
        for sa in stock_alerts:
            code = sa['stock_code']
            name = sa['stock_name']
            level = sa['level']
            lines.append(f"### {code} {name} ({level})")
            lines.append(f"")
            for a in sa['alerts']:
                lines.append(f"- {a}")
            lines.append(f"")
    else:
        lines.append(f"## 个股风险提示")
        lines.append(f"")
        lines.append(f"所有持仓通过风控检查，无异常。")
        lines.append(f"")

    return '\n'.join(lines)


def push_risk_report(user_id: int, env: str = 'online') -> int:
    """
    Generate risk report and push to user's inbox.

    Returns:
        Message ID of the created inbox message.
    """
    from api.services.inbox_service import create_message

    report_content = generate_risk_report(user_id, env=env)

    today = datetime.now().strftime('%Y-%m-%d')
    title = f"持仓风控日报 {today}"

    msg_id = create_message(
        user_id=user_id,
        message_type='daily_report',
        title=title,
        content=report_content,
        metadata={'report_type': 'risk_scan', 'date': today},
        env=env,
    )

    logger.info('[DAILY_REPORT] pushed risk report to user=%s msg_id=%s', user_id, msg_id)
    return msg_id
