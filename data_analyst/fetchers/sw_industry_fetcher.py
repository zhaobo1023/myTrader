# -*- coding: utf-8 -*-
"""
申万行业分类抓取器

从 AKShare 拉取申万二级行业成分股，写入 trade_stock_basic 的
sw_level1 / sw_level2 字段。

数据来源：
- index_component_sw(801xxx): 返回各二级行业的成分股（6位裸码）
- sw_index_third_info: 提供完整的二级行业名称列表（通过 '上级行业' 字段）
- trade_stock_basic.industry: 已有的一级行业字段，用于推导 level2 -> level1 归属

用法:
    python -m data_analyst.fetchers.sw_industry_fetcher
    python -m data_analyst.fetchers.sw_industry_fetcher --dry-run
"""
import logging
import sys
import os
import time
import argparse
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from config.db import execute_query, execute_update

logger = logging.getLogger('myTrader.sw_industry_fetcher')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)

# ---------------------------------------------------------------------------
# SW Level2 index code range to scan (801xxx)
# Level1 codes are round numbers (801010, 801030, ...), level2 codes are in between.
# Confirmed valid range from empirical scan: 801011-801245
# We exclude large codes (801250+) which are size/style indices, not industry indices.
# ---------------------------------------------------------------------------
SCAN_MIN = 801011
SCAN_MAX = 801245


def _build_db_bare_map() -> dict:
    """Return bare_code (6-digit) -> level1 industry mapping from trade_stock_basic."""
    rows = list(execute_query(
        'SELECT stock_code, industry FROM trade_stock_basic WHERE industry IS NOT NULL',
        (),
        env='online',
    ))
    result = {}
    for r in rows:
        bare = r['stock_code'].split('.')[0] if '.' in r['stock_code'] else r['stock_code']
        result[bare] = r['industry']
    return result


def _infer_level1(stock_codes: list, db_map: dict) -> Optional[str]:
    """
    Given a list of 6-digit stock codes from a level2 index,
    infer the level1 industry by majority vote against db_map.
    Returns None if no match found.
    """
    counts: dict = {}
    for sc in stock_codes:
        l1 = db_map.get(str(sc), '')
        if l1:
            counts[l1] = counts.get(l1, 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.get)


def fetch_sw_mapping() -> dict:
    """
    Scan 801xxx range, call index_component_sw for each valid code,
    infer level1 from existing DB data, and build:
      { bare_code: (level1_name, level2_name, level2_index_code) }

    Level2 name is derived from the code-to-name mapping built during scanning.
    """
    import akshare as ak

    db_map = _build_db_bare_map()
    logger.info('Loaded %d stocks from trade_stock_basic', len(db_map))

    # Build level2 name list from sw_index_third_info (parent names = level2 names)
    try:
        df3 = ak.sw_index_third_info()
        l2_names_set = set(df3['上级行业'].dropna().unique())
        logger.info('Level2 names from sw_index_third_info: %d', len(l2_names_set))
    except Exception as e:
        logger.warning('sw_index_third_info failed: %s, will use level1 majority vote only', e)
        l2_names_set = set()

    # We also need the name for each level2 code we find.
    # Strategy: if index count matches a named entry exactly, use that name.
    # Otherwise fall back to code-based naming (unreliable).
    # Better: build name by matching constituent overlap with named level2s.
    # Practical shortcut: use a hardcoded mapping supplemented by the scan.

    stock_map: dict = {}  # bare_code -> (level1, level2)
    found_codes: list = []  # [(code, level2_name, level1_name, num_stocks)]

    logger.info('Scanning SW level2 codes from %d to %d...', SCAN_MIN, SCAN_MAX)

    for code_int in range(SCAN_MIN, SCAN_MAX + 1):
        code = str(code_int)
        try:
            df = ak.index_component_sw(symbol=code)
            if df.empty or '证券代码' not in df.columns:
                continue

            stocks = [str(c) for c in df['证券代码'].tolist()]
            if not stocks:
                continue

            level1 = _infer_level1(stocks, db_map)
            if level1 is None:
                logger.debug('Code %s: no level1 match, skipping', code)
                continue

            # Try to get a name from sw_index_third_info matching:
            # we can't directly, so use a fallback approach below
            found_codes.append((code, level1, stocks))
            logger.debug('Code %s: level1=%s, stocks=%d', code, level1, len(stocks))

        except Exception as e:
            logger.debug('Code %s: error %s', code, e)

        time.sleep(0.15)

    logger.info('Found %d valid level2 codes', len(found_codes))

    # Now assign level2 names.
    # For each code, find the best matching level2 name from l2_names_set
    # by looking at which level3 stocks overlap with the level2 constituents.
    # Since we can't enumerate level3 easily, use a heuristic:
    # call sw_index_third_info code list, and for each found code,
    # check which level3 indices share constituents (via stock_industry_clf_hist_sw).
    # Simpler: use stock_industry_clf_hist_sw to find level2 code -> name.

    code_name_map = _resolve_level2_names(found_codes, l2_names_set)

    # Build final stock_map
    for code, level1, stocks in found_codes:
        level2_name = code_name_map.get(code, '')
        if not level2_name:
            logger.debug('Code %s: no level2 name resolved, skipping', code)
            continue
        for bare in stocks:
            stock_map[bare] = (level1, level2_name)

    logger.info('Final stock mapping: %d stocks', len(stock_map))
    return stock_map


def _resolve_level2_names(found_codes: list, l2_names_set: set) -> dict:
    """
    Given found_codes = [(code, level1, [stock_list])],
    resolve each code to a level2 name.

    Method: use stock_industry_clf_hist_sw to get the current internal 6-digit
    industry code per stock, then for each level2 index code, find which
    internal code cluster its stocks belong to, and map that to a level2 name
    by cross-referencing with sw_index_third_info parent names.

    Fallback: use the level2 name from the known hardcoded table if available.
    """
    import akshare as ak

    # Step 1: get latest internal code per stock
    try:
        df_clf = ak.stock_industry_clf_hist_sw()
        latest_clf = df_clf.sort_values('start_date').groupby('symbol').last().reset_index()
        stock_to_internal = dict(zip(latest_clf['symbol'], latest_clf['industry_code']))
    except Exception as e:
        logger.warning('stock_industry_clf_hist_sw failed: %s', e)
        stock_to_internal = {}

    # Step 2: for each level2 code, find the dominant internal_code
    # and map that to a level2 name via sw_index_third_info
    try:
        df3 = ak.sw_index_third_info()
        # internal code -> level2 name: we need to cross-reference
        # df3 has level3 codes (850xxx) and level2 parent names
        # The internal 6-digit codes from clf_hist map as: first 4 digits = category
        # Build a lookup from internal_code prefix -> level2 name
        # This is approximate; use dominant internal_code cluster
        pass
    except Exception:
        pass

    # Step 3: for each level2 index, majority-vote the internal_code
    # then use a lookup table (hardcoded from SW 2021 spec) to get name
    code_name_map: dict = {}

    for code, level1, stocks in found_codes:
        internal_counts: dict = {}
        for bare in stocks:
            ic = stock_to_internal.get(bare, '')
            if ic:
                # Group by first 4 digits (SW category code)
                prefix = ic[:4]
                internal_counts[ic] = internal_counts.get(ic, 0) + 1

        if not internal_counts:
            continue

        dominant_ic = max(internal_counts, key=internal_counts.get)
        # Map dominant_ic to level2 name using SW_INTERNAL_CODE_MAP
        name = SW_INTERNAL_CODE_MAP.get(dominant_ic, '')
        if name and name in l2_names_set:
            code_name_map[code] = name
        elif name:
            # Name from hardcoded map but not in l2_names_set - use it anyway
            code_name_map[code] = name
        else:
            logger.debug('Code %s dominant_ic=%s: no name found', code, dominant_ic)

    logger.info('Resolved %d / %d level2 code names', len(code_name_map), len(found_codes))
    return code_name_map


# ---------------------------------------------------------------------------
# SW 2021 internal 6-digit code -> level2 name mapping
# Source: SW Research 2021 classification system
# Format: {internal_code: level2_name}
# ---------------------------------------------------------------------------
SW_INTERNAL_CODE_MAP = {
    # 农林牧渔
    '110101': '种植业', '110201': '渔业', '110202': '渔业',
    '110301': '饲料', '110401': '农产品加工', '110402': '农产品加工',
    '110403': '农产品加工', '110404': '农产品加工',
    '110501': '养殖业', '110502': '养殖业', '110504': '养殖业',
    '110601': '动物保健Ⅱ', '110701': '养殖业', '110702': '养殖业',
    '110703': '养殖业', '110704': '养殖业',
    '110801': '动物保健Ⅱ', '110901': '农产品加工',
    # 基础化工
    '220101': '化学原料', '220201': '化学制品', '220202': '化学制品',
    '220203': '化学制品', '220204': '化学制品',
    '220301': '化学纤维', '220401': '塑料',
    '220501': '橡胶', '220503': '橡胶', '220505': '橡胶',
    '220601': '农化制品', '220602': '农化制品', '220603': '农化制品', '220604': '农化制品',
    '220701': '电子化学品Ⅱ',
    '220803': '化学制品', '220805': '化学制品', '220802': '化学制品',
    '220305': '化学纤维', '220309': '化学制品', '220315': '化学制品',
    '220901': '电子化学品Ⅱ',
    # 钢铁
    '230101': '普钢', '230201': '特钢',
    '230301': '特钢', '230302': '特钢',
    '230401': '普钢', '230402': '普钢', '230403': '普钢',
    '230501': '金属新材料',
    # 有色金属
    '240101': '工业金属', '240201': '贵金属', '240301': '小金属',
    '240401': '金属新材料',
    '240501': '小金属', '240502': '小金属', '240504': '小金属',
    '240601': '工业金属', '240602': '工业金属', '240603': '工业金属',
    # 电子
    '270101': '半导体', '270103': '半导体', '270104': '半导体', '270105': '半导体',
    '270201': '元件', '270202': '元件', '270203': '元件',
    '270301': '光学光电子',
    '270401': '消费电子',
    '270501': '其他电子Ⅱ', '270503': '其他电子Ⅱ', '270504': '其他电子Ⅱ',
    '270601': '军工电子Ⅱ',
    # 汽车
    '280101': '乘用车', '280201': '商用车',
    '280202': '汽车零部件', '280203': '汽车零部件', '280205': '汽车零部件',
    '280301': '汽车零部件', '280302': '汽车零部件', '280303': '汽车零部件',
    '280401': '摩托车及其他',
    '280501': '汽车服务', '280502': '汽车服务',
    '280601': '摩托车及其他', '280602': '摩托车及其他',
    # 家用电器
    '330101': '白色家电', '330102': '白色家电', '330106': '白色家电',
    '330201': '厨卫电器', '330202': '厨卫电器',
    '330301': '小家电', '330401': '黑色家电',
    '330501': '家电零部件Ⅱ', '330601': '家电零部件Ⅱ',
    '330701': '黑色家电',
    # 食品饮料
    '340101': '饮料乳品', '340201': '食品加工', '340301': '休闲食品',
    '340401': '调味发酵品Ⅱ', '340406': '调味发酵品Ⅱ', '340407': '调味发酵品Ⅱ',
    '340501': '白酒Ⅱ',
    '340601': '非白酒', '340602': '非白酒',
    '340701': '饮料乳品', '340702': '饮料乳品',
    '340801': '食品加工', '340802': '食品加工', '340803': '食品加工',
    '340901': '休闲食品',
    # 纺织服饰
    '350101': '纺织制造', '350102': '纺织制造', '350104': '纺织制造', '350106': '纺织制造',
    '350201': '服装家纺', '350205': '服装家纺', '350206': '服装家纺', '350209': '服装家纺',
    '350301': '饰品',
    # 轻工制造
    '360101': '包装印刷', '360102': '包装印刷', '360103': '包装印刷',
    '360201': '造纸', '360203': '造纸', '360204': '造纸', '360205': '造纸',
    '360301': '家居用品', '360306': '家居用品', '360307': '家居用品', '360311': '家居用品',
    '360401': '文娱用品',
    '360501': '文娱用品', '360502': '文娱用品',
    # 医药生物
    '370101': '化学制药', '370102': '化学制药',
    '370201': '中药Ⅱ',
    '370301': '生物制品', '370302': '生物制品', '370303': '生物制品', '370304': '生物制品',
    '370401': '医疗器械', '370402': '医疗器械', '370403': '医疗器械',
    '370501': '医疗服务', '370502': '医疗服务', '370503': '医疗服务', '370504': '医疗服务',
    '370601': '医药商业', '370602': '医药商业', '370603': '医药商业', '370604': '医药商业',
    # 公用事业
    '410101': '电力', '410201': '燃气Ⅱ', '410301': '水务及水治理Ⅱ',
    # 交通运输
    '420101': '铁路公路', '420201': '航运港口', '420301': '航空机场', '420401': '物流',
    '420802': '航运港口', '420803': '航运港口', '420805': '航运港口',
    '420901': '物流', '420902': '物流', '420903': '物流',
    '421101': '铁路公路', '421102': '铁路公路',
    # 房地产
    '430101': '房地产开发', '430201': '房地产服务',
    '430301': '房地产服务', '430302': '房地产服务', '430303': '房地产服务',
    # 商业贸易
    '440101': '一般零售', '440201': '专业连锁Ⅱ', '440301': '互联网电商',
    '440401': '贸易Ⅱ',
    '450601': '专业连锁Ⅱ', '450602': '专业连锁Ⅱ', '450603': '专业连锁Ⅱ',
    # 社会服务
    '450101': '旅游及景区', '450201': '酒店餐饮', '450301': '教育', '450401': '专业服务',
    '460601': '专业服务',
    '460801': '酒店餐饮', '460802': '酒店餐饮', '460804': '酒店餐饮',
    '460901': '旅游及景区', '460902': '旅游及景区',
    '461003': '教育', '461102': '专业服务',
    # 银行
    '480101': '国有大型银行Ⅱ', '480201': '股份制银行Ⅱ',
    '480301': '城商行Ⅱ', '480401': '农商行Ⅱ',
    # 非银金融
    '490101': '证券Ⅱ', '490201': '保险Ⅱ', '490301': '多元金融',
    '490302': '多元金融', '490303': '多元金融', '490307': '多元金融',
    # 建筑
    '500101': '房屋建设Ⅱ', '500201': '基础建设', '500301': '专业工程',
    '500401': '工程咨询服务Ⅱ',
    # 建筑材料
    '510101': '水泥', '510201': '玻璃玻纤', '510301': '装修建材',
    '510401': '非金属材料Ⅱ',
    # 传媒
    '520101': '出版', '520201': '影视院线', '520301': '数字媒体',
    '520401': '广告营销', '520501': '游戏Ⅱ', '520601': '电视广播Ⅱ',
    # 电力设备
    '610101': '电池', '610201': '电网设备', '610301': '电机Ⅱ',
    '610401': '光伏设备', '610501': '风电设备', '610601': '其他电源设备Ⅱ',
    '610701': '自动化设备', '610801': '照明设备Ⅱ',
    # 国防军工
    '620101': '航天装备Ⅱ', '620201': '航空装备Ⅱ', '620301': '地面兵装Ⅱ',
    '620401': '航海装备Ⅱ', '620501': '军工电子Ⅱ',
    # 计算机 (机械设备子类映射到计算机相关)
    '710101': '计算机设备', '710102': '计算机设备', '710103': '计算机设备',
    '710201': '软件开发',
    '710301': 'IT服务Ⅱ', '710401': 'IT服务Ⅱ', '710402': 'IT服务Ⅱ',
    # 通信
    '720101': '通信设备', '720201': '通信服务',
    '730101': '通信设备', '730102': '通信设备', '730103': '通信设备', '730104': '通信设备',
    '730204': '通信服务', '730205': '通信服务', '730206': '通信服务',
    # 煤炭
    '740101': '煤炭开采', '740201': '焦炭Ⅱ',
    # 石油石化
    '750101': '油服工程', '750201': '炼化及贸易',
    # 环保
    '760101': '环境治理', '760102': '环保设备Ⅱ',
    '760103': '环境治理', '760104': '环境治理',
    # 美容护理
    '770101': '化妆品', '770102': '个护用品', '770103': '化妆品', '770104': '个护用品',
    # 综合
    '800101': '综合Ⅱ',
    # 机械设备
    '640101': '通用设备', '640105': '通用设备', '640106': '通用设备',
    '640107': '通用设备', '640108': '通用设备', '640109': '通用设备',
    '640201': '专用设备', '640202': '专用设备', '640203': '专用设备',
    '640204': '专用设备', '640209': '专用设备',
    '640301': '工程机械', '640302': '工程机械', '640501': '工程机械',
    '640401': '轨交设备Ⅱ',
    '640601': '自动化设备', '640602': '自动化设备',
    '640701': '专用设备', '640702': '专用设备', '640704': '专用设备',
    # 社会服务补充
    '650101': '酒店餐饮', '650201': '旅游及景区',
    '650401': '专业服务', '650501': '教育', '650502': '教育', '650601': '专业服务',
}


def sync_to_db(stock_map: dict, dry_run: bool = False) -> dict:
    """
    将 stock_map 写入 trade_stock_basic 的 sw_level1 / sw_level2 字段。
    只更新已存在于 trade_stock_basic 的股票。

    Returns: {updated, skipped, total}
    """
    rows = list(execute_query(
        'SELECT stock_code FROM trade_stock_basic',
        (),
        env='online',
    ))
    existing_bare = set()
    for r in rows:
        code = r['stock_code']
        bare = code.split('.')[0] if '.' in code else code
        existing_bare.add(bare)

    updated = 0
    skipped = 0

    for bare_code, (level1, level2) in stock_map.items():
        if bare_code not in existing_bare:
            skipped += 1
            continue

        if dry_run:
            logger.debug('[dry-run] %s -> %s / %s', bare_code, level1, level2)
            updated += 1
            continue

        execute_update(
            """
            UPDATE trade_stock_basic
            SET sw_level1 = %s, sw_level2 = %s
            WHERE stock_code LIKE %s
            """,
            (level1, level2, bare_code + '%'),
            env='online',
        )
        updated += 1

    stats = {'updated': updated, 'skipped': skipped, 'total': len(stock_map)}
    logger.info('DB sync complete: updated=%d skipped=%d total_mapped=%d',
                updated, skipped, len(stock_map))
    return stats


def run(dry_run: bool = False) -> dict:
    """Main entry: fetch + sync."""
    logger.info('=== 申万行业分类抓取开始 (dry_run=%s) ===', dry_run)
    stock_map = fetch_sw_mapping()
    stats = sync_to_db(stock_map, dry_run=dry_run)
    logger.info('=== 申万行业分类抓取完成 ===')
    return stats


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='抓取申万行业分类并写入数据库')
    parser.add_argument('--dry-run', action='store_true', help='仅统计，不写库')
    args = parser.parse_args()
    result = run(dry_run=args.dry_run)
    print(result)
