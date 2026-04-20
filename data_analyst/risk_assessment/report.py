# -*- coding: utf-8 -*-

from data_analyst.risk_assessment.schemas import LayeredRiskResult, StockRiskResult, DataStatus


_STATUS_LABEL = {
    'ok': '[OK]',
    'stale': '[WARN]',
    'no_data': '[RED]',
    'auto_triggered': '[OK] (已自动触发)',
    'trigger_failed': '[RED] (触发失败)',
}

_LEVEL_LABEL = {
    'LOW': '[OK] 低风险',
    'MEDIUM': '[WARN] 中等风险',
    'HIGH': '[RED] 偏高风险',
    'CRITICAL': '[RED] 极高风险',
}


def _level_label(level: str) -> str:
    return _LEVEL_LABEL.get(level, level)


def _data_status_table(data_status: list) -> str:
    if not data_status:
        return '无数据状态信息\n'
    lines = [
        '| 数据源 | 最新日期 | 延迟(天) | 状态 |',
        '|--------|----------|----------|------|',
    ]
    for ds in data_status:
        status_label = _STATUS_LABEL.get(ds.status, ds.status)
        delay = str(ds.delay_days) if ds.delay_days >= 0 else 'N/A'
        lines.append('| {} | {} | {} | {} |'.format(
            ds.name, ds.latest_date or '-', delay, status_label
        ))
    return '\n'.join(lines) + '\n'


def _stock_section(stocks: list) -> str:
    if not stocks:
        return '无持仓个股数据\n'

    triggered = [s for s in stocks if s.stop_loss_hit or s.alerts]
    not_triggered = [s for s in stocks if not s.stop_loss_hit and not s.alerts]

    lines = []

    if triggered:
        lines.append('### 触发预警的个股\n')
        lines.append('| 代码 | 名称 | 综合分 | 财务 | 估值 | 情绪 | 技术 | 动量 | 止损 | 预警 |')
        lines.append('|------|------|--------|------|------|------|------|------|------|------|')
        for s in triggered:
            ss = s.sub_scores
            stop_flag = '[RED]触及' if s.stop_loss_hit else '-'
            alerts_str = '; '.join(s.alerts) if s.alerts else '-'
            lines.append('| {} | {} | {:.0f} | {:.0f} | {:.0f} | {:.0f} | {:.0f} | {:.0f} | {} | {} |'.format(
                s.stock_code, s.stock_name, s.score,
                ss.get('financial', 0), ss.get('valuation', 0),
                ss.get('news', 0), ss.get('technical', 0),
                ss.get('momentum', 0),
                stop_flag, alerts_str,
            ))
        lines.append('')

    if not_triggered:
        lines.append('### 正常持仓\n')
        lines.append('| 代码 | 名称 | 综合分 | 财务 | 估值 | 情绪 | 技术 | 动量 |')
        lines.append('|------|------|--------|------|------|------|------|------|')
        for s in not_triggered:
            ss = s.sub_scores
            lines.append('| {} | {} | {:.0f} | {:.0f} | {:.0f} | {:.0f} | {:.0f} | {:.0f} |'.format(
                s.stock_code, s.stock_name, s.score,
                ss.get('financial', 0), ss.get('valuation', 0),
                ss.get('news', 0), ss.get('technical', 0),
                ss.get('momentum', 0),
            ))
        lines.append('')

    return '\n'.join(lines)


def generate_report_v2(scan_result: LayeredRiskResult) -> str:
    """生成完整 Markdown 风控报告。"""
    r = scan_result
    macro = r.macro
    regime = r.regime
    sector = r.sector
    stocks = r.stocks

    triggered_count = sum(1 for s in stocks if s.stop_loss_hit or s.alerts)
    exec_score = 0.0
    exec_level = ''
    exec_alerts = []
    exec_suggestions = []
    position_count = 0
    max_positions = 10
    daily_loss_pct = 0.0
    st_stocks = []
    price_limit_stocks = []

    # exec 结果存在 overall_suggestions 之外，从 suggestion 推断
    # 实际上 exec_result 作为 dict 没有存入 LayeredRiskResult，
    # 此处通过读取 overall_suggestions 中包含执行层的内容进行展示即可

    lines = []

    # ---- 标题 ----
    lines.append('# 持仓风控日报 ({})\n'.format(r.scan_time[:10]))
    lines.append('> 扫描时间: {}  用户ID: {}\n'.format(r.scan_time, r.user_id))
    lines.append('')

    # ---- 数据状态 ----
    lines.append('## 数据状态\n')
    lines.append(_data_status_table(r.data_status))
    lines.append('')

    # ---- L1 宏观环境 ----
    lines.append('## L1 宏观环境 [风险: {:.0f}/100 | {} | 建议仓位: <={:.0f}%]\n'.format(
        macro.score,
        _level_label(macro.level),
        macro.suggested_max_exposure * 100,
    ))
    dim_scores = macro.details.get('dimension_scores', {})
    raw_values = macro.details.get('raw_values', {})
    if dim_scores:
        lines.append('| 维度 | 原始值 | 风险分 |')
        lines.append('|------|--------|--------|')
        dim_names = {
            'fear_index': '恐慌贪婪指数',
            'vix': 'VIX/QVIX',
            'northflow': '北向资金(5日均)',
            'yield_spread': '美债利差',
            'commodity': '美元指数(DXY)',
            'fx': '北向资金5日',
        }
        for k, v in dim_scores.items():
            raw = raw_values.get(k, '-')
            lines.append('| {} | {} | {:.0f} |'.format(dim_names.get(k, k), raw, v))
        lines.append('')
    if macro.suggestions:
        for s in macro.suggestions:
            lines.append('- {}'.format(s))
        lines.append('')

    # ---- L2 市场状态 ----
    lines.append('## L2 市场状态 [风险: {:.0f}/100 | {}]\n'.format(
        regime.score, _level_label(regime.level)
    ))
    if regime.market_state:
        lines.append('- 市场状态: {}'.format(regime.market_state))
    mutation = regime.details.get('is_mutation', False)
    lines.append('- 结构突变: {}'.format('[RED] 是' if mutation else '[OK] 否'))
    lines.append('- 持仓平均相关性: {:.3f}'.format(regime.avg_correlation))
    if regime.high_corr_pairs:
        lines.append('- 高相关对(相关性>0.6):')
        for a, b, c in regime.high_corr_pairs[:5]:
            lines.append('  - {} & {} (corr={:.3f})'.format(a, b, c))
    if regime.suggestions:
        lines.append('')
        for s in regime.suggestions:
            lines.append('- {}'.format(s))
    lines.append('')

    # ---- L3 行业暴露 ----
    lines.append('## L3 行业暴露 [风险: {:.0f}/100 | {}]\n'.format(
        sector.score, _level_label(sector.level)
    ))
    if sector.industry_breakdown:
        lines.append('| 行业 | 仓位占比 |')
        lines.append('|------|----------|')
        for ind, ratio in sorted(sector.industry_breakdown.items(), key=lambda x: -x[1]):
            lines.append('| {} | {:.1f}% |'.format(ind, ratio * 100))
        lines.append('')
    if sector.overvalued_industries:
        lines.append('- 高估行业(5年PE分位>70%): {}'.format('、'.join(sector.overvalued_industries)))
    if sector.suggestions:
        for s in sector.suggestions:
            lines.append('- {}'.format(s))
    lines.append('')

    # ---- L4 个股预警 ----
    lines.append('## L4 个股预警 [{} 只触发]\n'.format(triggered_count))
    lines.append(_stock_section(stocks))

    # ---- L5 交易规则 ----
    lines.append('## L5 交易规则\n')
    lines.append('持仓数量: {}'.format(len(stocks)))
    lines.append('')

    # 从 overall_suggestions 中筛选执行层相关内容（ST/涨跌停/仓位）
    exec_keywords = ['ST股票', '涨跌停', '持仓数量', '今日持仓整体亏损', '单仓占比', '交易规则']
    exec_items = [s for s in r.overall_suggestions if any(kw in s for kw in exec_keywords)]
    if exec_items:
        for item in exec_items:
            lines.append('- [WARN] {}'.format(item))
    else:
        lines.append('- [OK] 交易规则检查通过')
    lines.append('')

    # ---- 综合建议 ----
    lines.append('## 综合建议\n')
    lines.append('**综合风险评分: {:.0f}/100 | {}**\n'.format(
        r.overall_score, _level_label(
            'CRITICAL' if r.overall_score >= 70 else
            'HIGH' if r.overall_score >= 50 else
            'MEDIUM' if r.overall_score >= 30 else 'LOW'
        )
    ))
    if r.overall_suggestions:
        for i, s in enumerate(r.overall_suggestions, 1):
            lines.append('{}. {}'.format(i, s))
    else:
        lines.append('暂无具体建议')
    lines.append('')

    # ---- 各层评分汇总 ----
    lines.append('## 评分汇总\n')
    lines.append('| 层级 | 评分 | 等级 |')
    lines.append('|------|------|------|')
    lines.append('| L1 宏观环境 | {:.0f} | {} |'.format(macro.score, macro.level))
    lines.append('| L2 市场状态 | {:.0f} | {} |'.format(regime.score, regime.level))
    lines.append('| L3 行业暴露 | {:.0f} | {} |'.format(sector.score, sector.level))
    stocks_avg = round(sum(s.score for s in stocks) / len(stocks), 1) if stocks else 50.0
    lines.append('| L4 个股均分 | {:.0f} | - |'.format(stocks_avg))
    lines.append('| 综合评分 | {:.0f} | {} |'.format(
        r.overall_score,
        'CRITICAL' if r.overall_score >= 70 else
        'HIGH' if r.overall_score >= 50 else
        'MEDIUM' if r.overall_score >= 30 else 'LOW'
    ))
    lines.append('')

    return '\n'.join(lines)
