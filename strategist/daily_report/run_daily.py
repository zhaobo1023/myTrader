# -*- coding: utf-8 -*-
"""
持仓个股日报生成器

每日盘后执行：
1. 查询所有有活跃持仓的注册用户
2. 按用户聚合持仓个股，拉取当日技术面数据
3. 检查并补抓当日公告（全市场，去重）
4. 用 LLM 生成日报 Markdown
5. 写入各用户信箱（message_type='daily_report'）

调用方式：
    python -m strategist.daily_report.run_daily
    python -m strategist.daily_report.run_daily --dry-run   # 只打印不写库
"""
import argparse
import logging
import os
import sys
from datetime import date
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config.db import execute_query, execute_update  # noqa: E402

logger = logging.getLogger('myTrader.daily_report')


# ---------------------------------------------------------------------------
# 数据采集
# ---------------------------------------------------------------------------

def _get_active_users_with_positions() -> list[dict]:
    """
    查询所有有活跃持仓且开启日报推送的用户及其持仓。
    未配置通知偏好的用户视为默认开启（LEFT JOIN + COALESCE）。
    """
    rows = execute_query(
        """
        SELECT u.id AS user_id, u.display_name, u.email,
               p.stock_code, p.stock_name, p.level, p.shares, p.cost_price
        FROM users u
        JOIN user_positions p ON p.user_id = u.id
        LEFT JOIN user_notification_configs nc ON nc.user_id = u.id
        WHERE p.is_active = 1
          AND u.is_active = 1
          AND COALESCE(nc.daily_report_enabled, 1) = 1
        ORDER BY u.id, p.level, p.stock_code
        """,
        env='online',
    )
    # 按用户分组
    users: dict = {}
    for r in rows:
        uid = r['user_id']
        if uid not in users:
            users[uid] = {
                'user_id': uid,
                'display_name': r['display_name'] or f'用户{uid}',
                'email': r['email'] or '',
                'positions': [],
            }
        users[uid]['positions'].append({
            'stock_code': r['stock_code'],
            'stock_name': r['stock_name'] or r['stock_code'],
            'level': r['level'] or '',
            'shares': r['shares'],
            'cost_price': float(r['cost_price']) if r['cost_price'] else None,
        })
    return list(users.values())


def _fetch_tech_data(codes: list[str]) -> dict:
    """
    拉取最近6个交易日数据，计算日涨跌幅、5日涨跌幅、量比。
    返回 {code: {close, chg_pct, chg_5d_pct, vol_ratio, trade_date, high, low}}
    """
    if not codes:
        return {}
    placeholders = ', '.join(['%s'] * len(codes))
    try:
        rows = execute_query(
            """
            SELECT sub.stock_code, sub.close_price, sub.open_price,
                   sub.high_price, sub.low_price, sub.volume, sub.trade_date, sub.rn
            FROM (
                SELECT stock_code, close_price, open_price, high_price, low_price,
                       volume, trade_date,
                       ROW_NUMBER() OVER (PARTITION BY stock_code ORDER BY trade_date DESC) AS rn
                FROM trade_stock_daily
                WHERE stock_code IN ({})
            ) sub
            WHERE sub.rn <= 6
            """.format(placeholders),
            tuple(codes),
            env='online',
        )
    except Exception as e:
        logger.warning('[daily_report] tech data query failed: %s', e)
        return {}

    raw: dict = {}
    for r in rows:
        raw.setdefault(r['stock_code'], []).append(r)

    result = {}
    for code, recs in raw.items():
        recs_sorted = sorted(recs, key=lambda x: x['rn'])
        latest = recs_sorted[0]
        prev = recs_sorted[1] if len(recs_sorted) > 1 else None
        day5 = recs_sorted[5] if len(recs_sorted) > 5 else None

        close = float(latest['close_price']) if latest['close_price'] else None
        prev_close = float(prev['close_price']) if prev and prev['close_price'] else None
        close_5d = float(day5['close_price']) if day5 and day5['close_price'] else None
        vol = int(latest['volume']) if latest['volume'] else None
        prev_vol = int(prev['volume']) if prev and prev['volume'] else None

        result[code] = {
            'trade_date': str(latest['trade_date']) if latest['trade_date'] else '',
            'close': close,
            'high': float(latest['high_price']) if latest['high_price'] else None,
            'low': float(latest['low_price']) if latest['low_price'] else None,
            'chg_pct': round((close - prev_close) / prev_close * 100, 2) if close and prev_close else None,
            'chg_5d_pct': round((close - close_5d) / close_5d * 100, 2) if close and close_5d else None,
            'vol_ratio': round(vol / prev_vol, 2) if vol and prev_vol and prev_vol > 0 else None,
        }
    return result


def _ensure_today_announcements(today: date) -> bool:
    """
    检查今日公告是否已抓取，没有则触发全市场抓取。
    使用 announcement_fetch_lock 表的 INSERT IGNORE 保证幂等，
    防止调度器和 API 并发重复触发。
    返回 True 表示本次触发了抓取。
    """
    today_str = today.isoformat()
    try:
        execute_update(
            """CREATE TABLE IF NOT EXISTS announcement_fetch_lock (
                fetch_date DATE NOT NULL,
                status VARCHAR(10) NOT NULL DEFAULT 'fetching',
                created_at DATETIME NOT NULL,
                PRIMARY KEY (fetch_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
            env='online',
        )
        inserted = execute_update(
            """INSERT IGNORE INTO announcement_fetch_lock (fetch_date, status, created_at)
               VALUES (%s, 'fetching', NOW())""",
            (today_str,),
            env='online',
        )
        if not inserted:
            logger.info('[daily_report] announcements for %s already fetched/in-progress, skip', today_str)
            return False
    except Exception as e:
        logger.warning('[daily_report] announcement lock check failed: %s', e)
        return False

    logger.info('[daily_report] fetching announcements for %s', today_str)
    try:
        from data_analyst.fetchers.announcement_fetcher import fetch_announcements_for_date
        fetch_announcements_for_date(today)
        execute_update(
            "UPDATE announcement_fetch_lock SET status='done' WHERE fetch_date=%s",
            (today_str,),
            env='online',
        )
        return True
    except Exception as e:
        execute_update(
            "UPDATE announcement_fetch_lock SET status='error' WHERE fetch_date=%s",
            (today_str,),
            env='online',
        )
        logger.warning('[daily_report] announcement fetch failed: %s', e)
        return False


def _get_announcements(codes: list[str], days: int = 7) -> dict:
    """查询指定股票近 N 日公告，返回 {code: [ann, ...]}。"""
    try:
        from data_analyst.fetchers.announcement_fetcher import get_announcements_for_codes
        return get_announcements_for_codes(codes, days=days)
    except Exception as e:
        logger.warning('[daily_report] get announcements failed: %s', e)
        return {}


# ---------------------------------------------------------------------------
# 日报生成
# ---------------------------------------------------------------------------

_SYS_PROMPT = """你是一个专业的A股持仓分析助手，负责生成每日持仓个股日报。
要求：
1. 语言简洁专业，每支股票分析控制在3-5句话
2. 公告分析要点明方向（利好/利空/中性）和影响程度
3. 技术面重点关注异常量价（量比>2为放量，涨跌>3%为显著）
4. 禁止使用任何 emoji 字符
5. 禁止凭空编造数据，只分析给定数据"""

_ANN_TYPE_LABEL = {
    'reduce': '减持', 'increase': '增持', 'buyback': '回购',
    'earnings_guide': '业绩预告', 'dividend': '分红', 'major_contract': '重大合同',
    'acquisition': '收购', 'restructure': '重组', 'placement': '定增',
    'convertible': '可转债', 'risk_warning': '风险提示', 'equity_incentive': '股权激励',
    'unlock': '解除限售', 'other': '其他',
}


def _build_prompt(user_info: dict, tech_map: dict, ann_map: dict, today: date) -> str:
    lines = [
        f'日期：{today.isoformat()}',
        f'用户持仓共 {len(user_info["positions"])} 支个股，请逐一分析：',
        '',
    ]

    for p in user_info['positions']:
        code = p['stock_code']
        name = p['stock_name']
        level = p['level']
        cost = p['cost_price']
        t = tech_map.get(code, {})
        anns = ann_map.get(code, [])

        # 技术面摘要，缺失字段明确标注"暂缺"，避免 LLM 自行推断
        tech_parts = []
        if t.get('close') is not None:
            close = t['close']
            tech_parts.append(f'收盘价={close}')
            if t.get('chg_pct') is not None:
                sign = '+' if t['chg_pct'] > 0 else ''
                tech_parts.append(f'日涨跌={sign}{t["chg_pct"]}%')
            else:
                tech_parts.append('日涨跌=暂缺')
            if t.get('chg_5d_pct') is not None:
                sign = '+' if t['chg_5d_pct'] > 0 else ''
                tech_parts.append(f'5日涨跌={sign}{t["chg_5d_pct"]}%')
            else:
                tech_parts.append('5日涨跌=暂缺')
            if t.get('vol_ratio') is not None:
                tech_parts.append(f'量比={t["vol_ratio"]}')
            else:
                tech_parts.append('量比=暂缺')
            if cost:
                cost_pct = round((close - cost) / cost * 100, 2)
                sign = '+' if cost_pct > 0 else ''
                tech_parts.append(f'持仓盈亏={sign}{cost_pct}%')
        else:
            tech_parts.append('暂无行情数据')

        lines.append(f'## {name}（{code}，{level}）')
        lines.append(f'技术面：{" | ".join(tech_parts)}')

        if anns:
            today_str = today.isoformat()
            today_anns = [a for a in anns if a['date'] == today_str]
            recent_anns = [a for a in anns if a['date'] != today_str]
            if today_anns:
                lines.append(f'今日公告（{len(today_anns)}条）：')
                for a in today_anns[:3]:
                    label = _ANN_TYPE_LABEL.get(a['type'], a['type'])
                    lines.append(f'  [{label}] {a["title"]} ({a["direction"]})')
            if recent_anns:
                lines.append(f'近期公告（{len(recent_anns[:3])}条）：')
                for a in recent_anns[:3]:
                    label = _ANN_TYPE_LABEL.get(a['type'], a['type'])
                    lines.append(f'  [{label}/{a["date"]}] {a["title"]}')
        else:
            lines.append('公告：近7日无重大公告')

        lines.append('')

    lines.append('请为以上每支股票生成简洁的日报点评（每股3-5句话），最后给出整体持仓关注要点。')
    return '\n'.join(lines)


def _generate_report(prompt: str) -> str:
    try:
        import httpx
        from openai import OpenAI
        from investment_rag.config import DEFAULT_CONFIG
        cfg = DEFAULT_CONFIG
        client = OpenAI(
            api_key=cfg.llm_api_key,
            base_url=cfg.llm_base_url,
            http_client=httpx.Client(timeout=180.0),
        )
        resp = client.chat.completions.create(
            model=cfg.llm_model,
            messages=[
                {'role': 'system', 'content': _SYS_PROMPT},
                {'role': 'user', 'content': prompt},
            ],
            temperature=0.5,
            max_tokens=4096,
        )
        return resp.choices[0].message.content or ''
    except Exception as e:
        logger.error('[daily_report] LLM generate failed: %s', e)
        return f'日报生成失败：{e}'


# ---------------------------------------------------------------------------
# 写入信箱
# ---------------------------------------------------------------------------

def _send_to_inbox(user_id: int, title: str, content: str, dry_run: bool = False) -> None:
    if dry_run:
        logger.info('[daily_report][DRY-RUN] would send to user=%s title=%s', user_id, title)
        return
    try:
        execute_update(
            """INSERT INTO inbox_messages (user_id, message_type, title, content, is_read, created_at)
               VALUES (%s, 'daily_report', %s, %s, 0, NOW())""",
            (user_id, title[:200], content),
            env='online',
        )
        logger.info('[daily_report] sent to user=%s', user_id)
    except Exception as e:
        logger.error('[daily_report] inbox insert failed for user=%s: %s', user_id, e)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def run(dry_run: bool = False, target_date: Optional[date] = None) -> dict:
    today = target_date or date.today()
    logger.info('[daily_report] START date=%s dry_run=%s', today.isoformat(), dry_run)

    users = _get_active_users_with_positions()
    if not users:
        logger.info('[daily_report] no users with positions, exit')
        return {'users': 0, 'sent': 0}

    logger.info('[daily_report] %d users with positions', len(users))

    # 收集所有 unique 股票代码
    all_codes = list({p['stock_code'] for u in users for p in u['positions']})
    logger.info('[daily_report] unique stocks: %d', len(all_codes))

    # 技术面数据（批量一次查询）
    tech_map = _fetch_tech_data(all_codes)

    # 公告抓取（当日全市场，去重）
    _ensure_today_announcements(today)
    ann_map = _get_announcements(all_codes, days=7)

    # 按用户生成日报
    sent = 0
    title = f'持仓个股日报 {today.isoformat()}'
    for user in users:
        logger.info('[daily_report] generating for user=%s (%d positions)',
                    user['user_id'], len(user['positions']))
        try:
            prompt = _build_prompt(user, tech_map, ann_map, today)
            content = _generate_report(prompt)
            _send_to_inbox(user['user_id'], title, content, dry_run=dry_run)
            sent += 1
        except Exception as e:
            logger.error('[daily_report] failed for user=%s: %s', user['user_id'], e)

    logger.info('[daily_report] DONE users=%d sent=%d', len(users), sent)
    return {'users': len(users), 'sent': sent}


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        datefmt='%H:%M:%S',
    )
    parser = argparse.ArgumentParser(description='持仓个股日报生成器')
    parser.add_argument('--dry-run', action='store_true', help='不写入数据库，只打印')
    parser.add_argument('--date', default=None, help='指定日期 YYYY-MM-DD，默认今天')
    args = parser.parse_args()

    target_date = None
    if args.date:
        from datetime import datetime
        target_date = datetime.strptime(args.date, '%Y-%m-%d').date()

    result = run(dry_run=args.dry_run, target_date=target_date)
    logger.info('[daily_report] 完成：%s', result)


if __name__ == '__main__':
    main()
