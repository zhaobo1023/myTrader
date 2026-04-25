# -*- coding: utf-8 -*-
"""
Stock info fetcher - pull company profiles from CNInfo via AKShare

Fields: industry, province, city, website, main_business, business_scope, company_intro, listed_date

Table: trade_stock_info
Source: akshare stock_profile_cninfo (巨潮资讯)
Schedule: weekly (data rarely changes)

Run manually:
    DB_ENV=online python data_analyst/fetchers/stock_info_fetcher.py
    DB_ENV=online python data_analyst/fetchers/stock_info_fetcher.py --codes 600519.SH,000858.SZ
"""
import sys
import os
import time
import argparse
import logging

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config.db import execute_query, execute_update, execute_many

logger = logging.getLogger('myTrader.stock_info')

try:
    import akshare as ak
    HAS_AKSHARE = True
except ImportError:
    HAS_AKSHARE = False


CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS trade_stock_info (
    stock_code     VARCHAR(20)  NOT NULL PRIMARY KEY COMMENT 'e.g. 600519.SH',
    stock_name     VARCHAR(50)  DEFAULT NULL,
    industry       VARCHAR(100) DEFAULT NULL COMMENT 'CNInfo industry',
    province       VARCHAR(30)  DEFAULT NULL COMMENT 'extracted from registered address',
    city           VARCHAR(30)  DEFAULT NULL,
    listed_date    DATE         DEFAULT NULL,
    website        VARCHAR(200) DEFAULT NULL,
    email          VARCHAR(100) DEFAULT NULL,
    phone          VARCHAR(50)  DEFAULT NULL,
    main_business  TEXT         DEFAULT NULL COMMENT 'main business description',
    business_scope TEXT         DEFAULT NULL COMMENT 'business scope',
    company_intro  TEXT         DEFAULT NULL COMMENT 'company introduction',
    reg_address    VARCHAR(200) DEFAULT NULL,
    office_address VARCHAR(200) DEFAULT NULL,
    updated_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX ix_stock_info_industry (industry),
    INDEX ix_stock_info_province (province)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def _norm_code(raw_code: str) -> str:
    """Convert raw 6-digit code to suffixed format: 600519 -> 600519.SH, 000858 -> 000858.SZ"""
    c = raw_code.strip()
    if '.' in c:
        return c
    if c.startswith(('6', '9')):
        return c + '.SH'
    return c + '.SZ'


def _extract_province_city(address: str):
    """Extract province and city from address string."""
    if not address:
        return None, None
    addr = address.strip()
    # Common province patterns
    provinces = [
        '北京', '天津', '上海', '重庆',
        '黑龙江', '吉林', '辽宁', '内蒙古',
        '河北', '河南', '山东', '山西', '陕西',
        '江苏', '浙江', '安徽', '福建', '江西',
        '湖北', '湖南', '广东', '广西', '海南',
        '四川', '贵州', '云南', '西藏',
        '甘肃', '青海', '宁夏', '新疆',
    ]
    province = None
    for p in provinces:
        if addr.startswith(p):
            province = p
            break
    if not province:
        return None, None

    # City extraction: province + 2-3 chars
    rest = addr[len(province):]
    city = None
    # Direct municipalities
    if province in ('北京', '天津', '上海', '重庆'):
        city = province
    elif rest:
        # Take first 2-3 chars as city (common pattern)
        for end_char in ('市', '州', '地区', '盟'):
            idx = rest.find(end_char)
            if idx > 0:
                city_candidate = rest[:idx + len(end_char)]
                if 2 <= len(city_candidate) <= 6:
                    city = city_candidate
                break
        if not city and len(rest) >= 2:
            city = rest[:3]

    return province, city


def _ensure_table(env: str):
    """Create table if not exists."""
    execute_update(CREATE_TABLE_SQL, env=env)
    logger.info('[stock_info] table ensured')


def fetch_single(code_raw: str, env: str) -> bool:
    """Fetch profile for a single stock and upsert."""
    if not HAS_AKSHARE:
        logger.error('[stock_info] akshare not installed')
        return False

    try:
        df = ak.stock_profile_cninfo(symbol=code_raw)
        if df is None or df.empty:
            return False
        row = df.iloc[0]
    except Exception as e:
        logger.warning('[stock_info] fetch failed for %s: %s', code_raw, e)
        return False

    stock_code = _norm_code(str(row.get('A股代码', code_raw)))
    stock_name = str(row.get('A股简称', '')) or None
    industry = str(row.get('所属行业', '')) or None
    if industry in ('nan', 'None', ''):
        industry = None

    reg_address = str(row.get('注册地址', '')) or None
    if reg_address in ('nan', 'None'):
        reg_address = None
    office_address = str(row.get('办公地址', '')) or None
    if office_address in ('nan', 'None'):
        office_address = None

    province, city = _extract_province_city(reg_address or office_address or '')

    listed_date_val = row.get('上市日期')
    listed_date = None
    if listed_date_val and str(listed_date_val) not in ('nan', 'None', 'NaT', ''):
        try:
            listed_date = str(pd.to_datetime(listed_date_val).date())
        except Exception:
            pass

    website = str(row.get('官方网站', '')) or None
    if website in ('nan', 'None', ''):
        website = None
    email = str(row.get('电子邮箱', '')) or None
    if email in ('nan', 'None', ''):
        email = None
    phone = str(row.get('联系电话', '')) or None
    if phone in ('nan', 'None', ''):
        phone = None

    main_business = str(row.get('主营业务', '')) or None
    if main_business in ('nan', 'None', ''):
        main_business = None
    business_scope = str(row.get('经营范围', '')) or None
    if business_scope in ('nan', 'None', ''):
        business_scope = None
    company_intro = str(row.get('机构简介', '')) or None
    if company_intro in ('nan', 'None', ''):
        company_intro = None

    sql = """
        INSERT INTO trade_stock_info
            (stock_code, stock_name, industry, province, city, listed_date,
             website, email, phone, main_business, business_scope,
             company_intro, reg_address, office_address, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
        ON DUPLICATE KEY UPDATE
            stock_name=VALUES(stock_name), industry=VALUES(industry),
            province=VALUES(province), city=VALUES(city), listed_date=VALUES(listed_date),
            website=VALUES(website), email=VALUES(email), phone=VALUES(phone),
            main_business=VALUES(main_business), business_scope=VALUES(business_scope),
            company_intro=VALUES(company_intro), reg_address=VALUES(reg_address),
            office_address=VALUES(office_address), updated_at=NOW()
    """
    execute_update(sql, (
        stock_code, stock_name, industry, province, city, listed_date,
        website, email, phone, main_business, business_scope,
        company_intro, reg_address, office_address,
    ), env=env)
    return True


def fetch_all(env: str = 'online', batch_size: int = 50, sleep_sec: float = 0.5):
    """Fetch profiles for all stocks in trade_stock_basic that don't have info yet, or all if force."""
    _ensure_table(env)

    rows = execute_query(
        'SELECT stock_code FROM trade_stock_basic WHERE stock_code IS NOT NULL',
        env=env,
    )
    all_codes = []
    for r in rows:
        code = r['stock_code']
        # Convert 600519.SH -> 600519 for akshare API
        raw = code.split('.')[0] if '.' in code else code
        all_codes.append((raw, code))

    # Check which codes already have data
    existing = set()
    try:
        info_rows = execute_query(
            'SELECT stock_code FROM trade_stock_info', env=env,
        )
        existing = {r['stock_code'] for r in info_rows}
    except Exception:
        pass

    todo = [(raw, full) for raw, full in all_codes if full not in existing]
    logger.info('[stock_info] total=%d existing=%d todo=%d', len(all_codes), len(existing), len(todo))

    if not todo:
        logger.info('[stock_info] all stocks already fetched')
        return

    success = 0
    fail = 0
    for i, (raw_code, full_code) in enumerate(todo):
        ok = fetch_single(raw_code, env)
        if ok:
            success += 1
        else:
            fail += 1

        if (i + 1) % 100 == 0:
            logger.info('[stock_info] progress: %d/%d (ok=%d fail=%d)', i + 1, len(todo), success, fail)

        if sleep_sec > 0:
            time.sleep(sleep_sec)

    logger.info('[stock_info] done: total=%d success=%d fail=%d', len(todo), success, fail)


def fetch_incremental(env: str = 'online'):
    """Fetch info only for new stocks (not yet in trade_stock_info)."""
    fetch_all(env=env, batch_size=0)


def fetch_by_codes(codes: list, env: str = 'online'):
    """Fetch info for specific stock codes."""
    _ensure_table(env)
    success = 0
    for code in codes:
        raw = code.split('.')[0] if '.' in code else code
        if fetch_single(raw, env):
            success += 1
        time.sleep(0.3)
    logger.info('[stock_info] fetched %d/%d codes', success, len(codes))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    parser = argparse.ArgumentParser(description='Fetch stock info from CNInfo')
    parser.add_argument('--env', default=os.environ.get('DB_ENV', 'online'), help='DB env')
    parser.add_argument('--codes', default=None, help='Comma-separated stock codes, e.g. 600519.SH,000858.SZ')
    parser.add_argument('--full', action='store_true', help='Force re-fetch all (including existing)')
    args = parser.parse_args()

    if args.codes:
        codes = [c.strip() for c in args.codes.split(',') if c.strip()]
        fetch_by_codes(codes, env=args.env)
    elif args.full:
        # Force re-fetch: clear existing data first
        _ensure_table(args.env)
        execute_update('TRUNCATE TABLE trade_stock_info', env=args.env)
        fetch_all(env=args.env)
    else:
        fetch_incremental(env=args.env)
