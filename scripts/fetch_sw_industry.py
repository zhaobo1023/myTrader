# -*- coding: utf-8 -*-
"""
scripts/fetch_sw_industry.py

补充 trade_stock_industry 申万一级行业分类数据（AKShare 接口）

策略：
  1. 通过 ak.sw_index_first_info() 获取申万一级行业列表
  2. 对每个行业，通过 ak.index_stock_cons_weight_csindex() 或
     ak.sw_index_cons() 获取成分股列表
  3. 插入 trade_stock_industry（classify_type='SW', industry_level='1'）

用法：
  DB_ENV=online python scripts/fetch_sw_industry.py

  # 仅同步缺失的股票（增量）
  DB_ENV=online python scripts/fetch_sw_industry.py --incremental
"""

import argparse
import os
import sys

_args_pre = sys.argv[1:]
if "--no-proxy" in _args_pre:
    for _var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy",
                 "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy"):
        os.environ.pop(_var, None)
    os.environ["NO_PROXY"] = "*"

import logging
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from config.db import execute_query, execute_many

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

try:
    import akshare as ak
except ImportError:
    logger.error("AKShare 未安装，请运行: pip install akshare")
    sys.exit(1)

DB_ENV = os.getenv("DB_ENV", "online")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_code(code: str) -> str:
    """
    AKShare 返回的代码格式不统一，统一转为 '000001.SZ' 格式。
    输入可能是 '000001' / '000001.SZ' / 'SZ000001' 等
    """
    code = str(code).strip()
    if "." in code:
        parts = code.split(".")
        if parts[1].upper() in ("SZ", "SH", "BJ"):
            return f"{parts[0]}.{parts[1].upper()}"
        return code
    if code.startswith(("00", "30", "002")):
        return f"{code}.SZ"
    elif code.startswith("6"):
        return f"{code}.SH"
    elif code.startswith(("83", "43", "87")):
        return f"{code}.BJ"
    return f"{code}.SZ"


def get_existing_codes() -> set[str]:
    rows = execute_query(
        "SELECT DISTINCT stock_code FROM trade_stock_industry WHERE classify_type='SW' AND industry_level='1'",
        env=DB_ENV,
    )
    return {r["stock_code"] for r in rows}


def get_all_stock_names() -> dict[str, str]:
    rows = execute_query("SELECT stock_code, stock_name FROM trade_stock_basic", env=DB_ENV)
    return {r["stock_code"]: r["stock_name"] for r in rows}


# ---------------------------------------------------------------------------
# Fetch SW industry list and constituents
# ---------------------------------------------------------------------------

def fetch_sw_industries() -> list[dict]:
    """
    Returns list of {industry_code, industry_name} for 申万一级行业.
    Uses ak.sw_index_first_info().
    """
    try:
        df = ak.sw_index_first_info()
        # Expected columns: '行业代码', '行业名称', ...
        df.columns = [str(c).strip() for c in df.columns]
        code_col = next((c for c in df.columns if "代码" in c), None)
        name_col = next((c for c in df.columns if "名称" in c), None)
        if not code_col or not name_col:
            logger.error(f"Unexpected columns from sw_index_first_info: {list(df.columns)}")
            return []
        return [
            {"industry_code": str(row[code_col]).strip(), "industry_name": str(row[name_col]).strip()}
            for _, row in df.iterrows()
        ]
    except Exception as e:
        logger.error(f"sw_index_first_info failed: {e}")
        return []


def fetch_sw_cons(industry_code: str) -> list[str]:
    """
    Returns list of stock codes for a given SW first-level industry code.
    Tries multiple AKShare APIs for compatibility.
    """
    # Method 1: ak.index_stock_cons_em (东方财富行业成分)
    # Method 2: ak.sw_index_cons (申万行业成分) - if available
    # Method 3: ak.index_stock_cons_weight_csindex

    # Try ak.sw_index_cons first (newer AKShare versions)
    try:
        df = ak.sw_index_cons(index_code=industry_code)
        if df is not None and not df.empty:
            df.columns = [str(c).strip() for c in df.columns]
            code_col = next(
                (c for c in df.columns if "代码" in c or "code" in c.lower()), None
            )
            if code_col:
                return [str(v).strip() for v in df[code_col].tolist() if v]
    except Exception:
        pass

    # Fallback: ak.index_stock_cons_em using industry name via code
    try:
        df = ak.index_stock_cons_em(symbol=industry_code)
        if df is not None and not df.empty:
            df.columns = [str(c).strip() for c in df.columns]
            code_col = next(
                (c for c in df.columns if "代码" in c or "code" in c.lower()), None
            )
            if code_col:
                return [str(v).strip() for v in df[code_col].tolist() if v]
    except Exception:
        pass

    logger.warning(f"[{industry_code}] Could not fetch SW constituents via either API")
    return []


# ---------------------------------------------------------------------------
# Alternative: derive from trade_stock_basic.industry (fast fallback)
# ---------------------------------------------------------------------------

def populate_from_stock_basic(envs: list[str]) -> int:
    """
    Fallback: copy industry data from trade_stock_basic.industry into
    trade_stock_industry with classify_type='SW', industry_level='1'.
    """
    source_env = envs[0]
    rows = execute_query(
        "SELECT stock_code, stock_name, industry FROM trade_stock_basic WHERE industry IS NOT NULL AND industry != ''",
        env=source_env,
    )
    if not rows:
        logger.warning("trade_stock_basic has no industry data")
        return 0

    data = []
    for r in rows:
        ind_name = r["industry"] or ""
        if not ind_name:
            continue
        data.append((
            r["stock_code"],
            r["stock_name"] or "",
            "",
            ind_name,
            "1",
            "SW",
        ))

    sql = """
        INSERT INTO trade_stock_industry
            (stock_code, stock_name, industry_code, industry_name, industry_level, classify_type)
        VALUES (%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            industry_name = VALUES(industry_name)
    """
    inserted = 0
    for env in envs:
        try:
            execute_many(sql, data, env=env)
            inserted = len(data)
            logger.info(f"[env={env}] Populated {len(data)} rows from trade_stock_basic.industry")
        except Exception as e:
            logger.error(f"[env={env}] DB insert failed: {e}")
    return inserted


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fetch SW industry classification")
    parser.add_argument("--incremental", action="store_true", help="Only insert missing stocks")
    parser.add_argument("--use-basic", action="store_true",
                        help="Use trade_stock_basic.industry as fallback (fast, no API calls)")
    parser.add_argument("--envs", default=os.getenv("DB_ENV", "online"),
                        help="Comma-separated DB envs to write (e.g. local,online)")
    parser.add_argument("--no-proxy", dest="no_proxy", action="store_true")
    args = parser.parse_args()

    envs = [e.strip() for e in args.envs.split(",") if e.strip()]
    primary_env = envs[0]
    logger.info(f"envs={envs}")

    # Fast path: use trade_stock_basic.industry
    if args.use_basic:
        n = populate_from_stock_basic(envs)
        logger.info(f"Done (basic fallback). Rows inserted: {n}")
        return

    existing = get_existing_codes() if args.incremental else set()
    names_map = get_all_stock_names()
    logger.info(f"Existing industry rows: {len(existing)}")

    # Fetch SW first-level industries
    industries = fetch_sw_industries()
    if not industries:
        logger.warning("SW industry list empty, falling back to trade_stock_basic.industry")
        n = populate_from_stock_basic(envs)
        logger.info(f"Done (fallback). Rows: {n}")
        return

    logger.info(f"SW first-level industries: {len(industries)}")

    total_inserted = 0
    for ind in industries:
        ind_code = ind["industry_code"]
        ind_name = ind["industry_name"]

        codes = fetch_sw_cons(ind_code)
        logger.info(f"  [{ind_name}] ({ind_code}) -> {len(codes)} stocks")
        time.sleep(0.3)

        if not codes:
            continue

        data = []
        for raw_code in codes:
            norm_code = normalize_code(raw_code)
            if args.incremental and norm_code in existing:
                continue
            stock_name = names_map.get(norm_code, "")
            data.append((
                norm_code,
                stock_name,
                ind_code,
                ind_name,
                "1",
                "SW",
            ))

        if not data:
            continue

        sql = """
            INSERT INTO trade_stock_industry
                (stock_code, stock_name, industry_code, industry_name, industry_level, classify_type)
            VALUES (%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE
                industry_code = VALUES(industry_code),
                industry_name = VALUES(industry_name)
        """
        for env in envs:
            try:
                execute_many(sql, data, env=env)
            except Exception as e:
                logger.error(f"[{ind_name}][env={env}] DB insert failed: {e}")
        total_inserted += len(data)
        existing.update(r[0] for r in data)

    logger.info(f"Done. Total rows inserted/updated: {total_inserted}")

    # If AKShare returned 0 constituents for all industries, fall back
    if total_inserted == 0:
        logger.warning("AKShare returned no constituents; using trade_stock_basic fallback")
        populate_from_stock_basic(envs)


if __name__ == "__main__":
    main()
