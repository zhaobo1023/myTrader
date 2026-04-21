# -*- coding: utf-8 -*-
"""
全市场重大公告抓取器

数据源: 东方财富 (via AKShare) - 沪深京 A 股公告大全
每日盘后一次调用，覆盖多个重大类型，写入 research_announcements 表。

调用方式:
    python -m data_analyst.fetchers.announcement_fetcher          # 抓今日
    python -m data_analyst.fetchers.announcement_fetcher --date 20260421
    python -m data_analyst.fetchers.announcement_fetcher --days 3  # 补抓最近N天
"""
import argparse
import logging
import time
from datetime import date, timedelta
from typing import Optional

from config.db import execute_query, execute_update

logger = logging.getLogger('myTrader.announcement_fetcher')

# ---------------------------------------------------------------------------
# 需要抓取的公告分类 (AKShare stock_notice_report symbol 参数)
# ---------------------------------------------------------------------------
FETCH_CATEGORIES = [
    ('重大事项', None),          # 包含收购/重大合同/业绩预告/定增等
    ('持股变动', None),          # 增减持/回购
    ('风险提示', None),          # ST预警/退市风险
    ('资产重组', None),          # 并购重组
]

# 公告类型关键词 -> ann_type 标准化
_TYPE_MAP = {
    '减持': 'reduce',
    '增持': 'increase',
    '回购': 'buyback',
    '业绩预告': 'earnings_guide',
    '业绩快报': 'earnings_guide',
    '利润分配': 'dividend',
    '分红': 'dividend',
    '重大合同': 'major_contract',
    '收购': 'acquisition',
    '重组': 'restructure',
    '定向增发': 'placement',
    '可转债': 'convertible',
    '风险': 'risk_warning',
    '退市': 'risk_warning',
    '股权激励': 'equity_incentive',
    '解除限售': 'unlock',
}

# 高价值类型 (direction 判断用)
_BULLISH_TYPES = {'increase', 'buyback', 'major_contract', 'acquisition'}
_BEARISH_TYPES = {'reduce', 'risk_warning', 'unlock'}


def _normalize_ann_type(ann_type_text: str, title: str) -> tuple[str, str, str]:
    """
    将东方财富公告类型文本标准化为 (ann_type, direction, magnitude)。
    ann_type: reduce/increase/buyback/earnings_guide/dividend/major_contract/...
    direction: positive/negative/neutral
    magnitude: high/medium/low
    """
    combined = ann_type_text + title

    ann_type = 'other'
    for kw, code in _TYPE_MAP.items():
        if kw in combined:
            ann_type = code
            break

    if ann_type in _BULLISH_TYPES:
        direction = 'positive'
        magnitude = 'high' if any(k in combined for k in ['重大', '大额', '战略']) else 'medium'
    elif ann_type in _BEARISH_TYPES:
        direction = 'negative'
        magnitude = 'high' if any(k in combined for k in ['大额', '清仓', '退市']) else 'medium'
    else:
        direction = 'neutral'
        magnitude = 'low'

    return ann_type, direction, magnitude


def fetch_announcements_for_date(target_date: date) -> dict:
    """
    抓取指定日期的全市场重大公告，写入 research_announcements。
    返回 {'fetched': int, 'new': int, 'errors': int}
    """
    try:
        import akshare as ak
    except ImportError:
        logger.error('akshare 未安装，请 pip install akshare')
        return {'fetched': 0, 'new': 0, 'errors': 1}

    date_str = target_date.strftime('%Y%m%d')
    date_iso = target_date.strftime('%Y-%m-%d')

    all_rows = []
    seen_keys = set()  # (code, title) 去重

    for category, _ in FETCH_CATEGORIES:
        try:
            df = ak.stock_notice_report(symbol=category, date=date_str)
            if df is None or df.empty:
                continue
            for _, row in df.iterrows():
                code_raw = str(row.get('代码', '')).strip().zfill(6)
                name = str(row.get('名称', '')).strip()
                title = str(row.get('公告标题', '')).strip()
                ann_type_text = str(row.get('公告类型', '')).strip()
                ann_date_val = str(row.get('公告日期', date_iso)).strip()[:10]
                url = str(row.get('网址', '')).strip()

                if not code_raw or not title:
                    continue

                # 标准化股票代码 (加交易所后缀)
                if code_raw.startswith('6'):
                    code = code_raw + '.SH'
                elif code_raw.startswith('8') or code_raw.startswith('4'):
                    code = code_raw + '.BJ'
                else:
                    code = code_raw + '.SZ'

                key = (code, title[:100])
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                ann_type, direction, magnitude = _normalize_ann_type(ann_type_text, title)
                all_rows.append((code, ann_date_val, ann_type, title, direction, magnitude, url))

            logger.info('[announcement] %s %s: %d rows', date_str, category, len(df))
            time.sleep(0.3)  # 礼貌性限速
        except Exception as e:
            logger.warning('[announcement] %s %s fetch failed: %s', date_str, category, e)

    if not all_rows:
        logger.info('[announcement] %s: no announcements found', date_str)
        return {'fetched': 0, 'new': 0, 'errors': 0}

    # 写入 research_announcements
    new_count = 0
    errors = 0
    for code, ann_date_val, ann_type, title, direction, magnitude, url in all_rows:
        try:
            execute_update(
                """INSERT INTO research_announcements
                       (code, ann_date, ann_type, title, direction, magnitude, pdf_url, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                   ON DUPLICATE KEY UPDATE
                       ann_type = VALUES(ann_type),
                       direction = VALUES(direction),
                       magnitude = VALUES(magnitude),
                       pdf_url = COALESCE(VALUES(pdf_url), pdf_url)""",
                (code, ann_date_val, ann_type, title[:299], direction, magnitude, url[:499]),
                env='online',
            )
            new_count += 1
        except Exception as e:
            logger.debug('[announcement] insert failed for %s %s: %s', code, title[:40], e)
            errors += 1

    logger.info('[announcement] %s done: fetched=%d written=%d errors=%d',
                date_str, len(all_rows), new_count, errors)
    return {'fetched': len(all_rows), 'new': new_count, 'errors': errors}


def fetch_announcements_recent(days: int = 1) -> dict:
    """抓取最近 N 个自然日的公告（用于补抓）。"""
    total = {'fetched': 0, 'new': 0, 'errors': 0}
    today = date.today()
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:  # 跳过周末
            continue
        result = fetch_announcements_for_date(d)
        for k in total:
            total[k] += result.get(k, 0)
    return total


def get_announcements_for_codes(codes: list, days: int = 7) -> dict:
    """
    查询指定股票代码列表的最近公告，返回 {code: [ann_dict, ...]}。
    供 V2 晨报个股分析使用。
    """
    if not codes:
        return {}

    cutoff = (date.today() - timedelta(days=days)).strftime('%Y-%m-%d')
    placeholders = ','.join(['%s'] * len(codes))

    try:
        rows = execute_query(
            """SELECT code, ann_date, ann_type, title, direction, magnitude, summary
               FROM research_announcements
               WHERE code IN ({}) AND ann_date >= %s
               ORDER BY ann_date DESC""".format(placeholders),
            tuple(codes) + (cutoff,),
            env='online',
        )
    except Exception as e:
        logger.warning('[announcement] query failed: %s', e)
        return {}

    result = {}
    for r in rows:
        code = r['code']
        if code not in result:
            result[code] = []
        result[code].append({
            'date': str(r['ann_date']),
            'type': r['ann_type'],
            'title': r['title'],
            'direction': r['direction'] or 'neutral',
            'magnitude': r['magnitude'] or 'low',
            'summary': r['summary'] or '',
        })
    return result


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        datefmt='%H:%M:%S',
    )

    parser = argparse.ArgumentParser(description='全市场重大公告抓取')
    parser.add_argument('--date', type=str, help='指定日期 YYYYMMDD，默认今天')
    parser.add_argument('--days', type=int, default=1, help='补抓最近N天（默认1=今天）')
    args = parser.parse_args()

    if args.date:
        d = date(int(args.date[:4]), int(args.date[4:6]), int(args.date[6:8]))
        result = fetch_announcements_for_date(d)
    else:
        result = fetch_announcements_recent(days=args.days)

    print('结果:', result)


if __name__ == '__main__':
    main()
