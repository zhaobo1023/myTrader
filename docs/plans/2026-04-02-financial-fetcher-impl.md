# Financial Fetcher Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a financial report data fetching module that pulls structured data from akshare, downloads PDF annual reports from cninfo, generates Markdown summaries, and ingests everything into ChromaDB via the existing investment_rag infrastructure.

**Architecture:** Module lives at `data_analyst/financial_fetcher/`. Structured data (income/balance/dividend/bank indicators) fetched from akshare, stored in 4 MySQL tables via `config.db`. PDF annual reports downloaded from cninfo. Markdown summaries generated and ingested into ChromaDB collection "financials" reusing `investment_rag`'s `ChromaClient` + `EmbeddingClient`.

**Tech Stack:** Python 3.10+, akshare, pandas, pymysql (via config.db), ChromaDB (via investment_rag), DashScope embedding API, requests, argparse

---

## Key Context for the Implementer

- **NO emoji** in any code, comments, reports, CSV, logs. Use `[RED]`, `[WARN]`, `[OK]` instead.
- **One import per line**, never combined.
- **DB connection:** `from config.db import execute_query, get_connection` (NOT sqlalchemy)
- **Module pattern:** `data_analyst/financial_fetcher/` uses `sys.path.insert(0, _PROJECT_ROOT)` for cross-package imports.
- **RAG reuse:** `from investment_rag.store.chroma_client import ChromaClient` and `from investment_rag.embeddings.embed_model import EmbeddingClient` (DashScope API, NOT local BGE-M3)
- **RAGConfig:** `from investment_rag.config import DEFAULT_CONFIG` to get chroma_persist_dir and embedding settings
- **DDL:** Define as module-level constants in schemas.py, execute via `cursor.execute()` in storage.py
- **Upsert:** Use `INSERT ... ON DUPLICATE KEY UPDATE` with UNIQUE KEY
- **Example code reference:** `~/Downloads/myTrader-example/` contains the original scripts to adapt from
- **Design doc:** `docs/plans/2026-04-02-financial-fetcher-design.md`

---

### Task 1: Package Structure and Config

**Files:**
- Create: `data_analyst/financial_fetcher/__init__.py`
- Create: `data_analyst/financial_fetcher/config.py`

**Step 1: Create `data_analyst/financial_fetcher/__init__.py`**

```python
# -*- coding: utf-8 -*-
"""financial_fetcher - structured financial data + PDF annual reports"""

from .config import FinancialFetcherConfig, DEFAULT_WATCH_LIST

__all__ = ['FinancialFetcherConfig', 'DEFAULT_WATCH_LIST']
```

**Step 2: Create `data_analyst/financial_fetcher/config.py`**

```python
# -*- coding: utf-8 -*-
"""financial fetcher config"""

from dataclasses import dataclass, field
from typing import Dict
from pathlib import Path

DEFAULT_WATCH_LIST: Dict[str, str] = {
    # banks
    "600015": "华夏银行",
    "600036": "招商银行",
    "601288": "农业银行",
    "600016": "民生银行",
    "601166": "兴业银行",
    "601169": "北京银行",
    "600919": "江苏银行",
    "002142": "宁波银行",
    # coal
    "601088": "中国神华",
    "600188": "兖矿能源",
}

REQUEST_INTERVAL = 1.5  # seconds between akshare API calls


@dataclass
class FinancialFetcherConfig:
    """config for financial fetcher"""
    watch_list: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_WATCH_LIST))
    db_env: str = "online"
    request_interval: float = REQUEST_INTERVAL
    output_dir: str = "/Users/zhaobo/Documents/notes/Finance/Output/financials"
    pdf_output_dir: str = "output/annual_reports"
    rag_collection: str = "financials"
```

**Step 3: Verify import**

Run: `cd /Users/zhaobo/data0/person/myTrader && python -c "from data_analyst.financial_fetcher.config import FinancialFetcherConfig; c = FinancialFetcherConfig(); print(len(c.watch_list), 'stocks')"`
Expected: `10 stocks`

**Step 4: Commit**

```bash
git add data_analyst/financial_fetcher/__init__.py data_analyst/financial_fetcher/config.py
git commit -m "feat(financial-fetcher): add config and package structure"
```

---

### Task 2: Schemas (DDL + Models)

**Files:**
- Create: `data_analyst/financial_fetcher/schemas.py`

**Step 1: Create `data_analyst/financial_fetcher/schemas.py`**

Adapted from example `fetcher.py` DDL. Key changes: remove sqlalchemy, use raw DDL for pymysql.

```python
# -*- coding: utf-8 -*-
"""DDL for financial tables"""

FINANCIAL_INCOME_DDL = """
CREATE TABLE IF NOT EXISTS financial_income (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL,
    stock_name VARCHAR(50),
    report_date DATE NOT NULL,
    report_type VARCHAR(20),
    revenue DOUBLE COMMENT 'revenue (yi)',
    net_profit DOUBLE COMMENT 'net profit (yi)',
    net_profit_yoy DOUBLE COMMENT 'yoy%',
    roe DOUBLE COMMENT 'ROE%',
    gross_margin DOUBLE COMMENT 'gross margin%',
    eps DOUBLE COMMENT 'EPS',
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_stock_date (stock_code, report_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='income statement';
"""

FINANCIAL_BALANCE_DDL = """
CREATE TABLE IF NOT EXISTS financial_balance (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL,
    stock_name VARCHAR(50),
    report_date DATE NOT NULL,
    total_assets DOUBLE COMMENT 'total assets (yi)',
    total_equity DOUBLE COMMENT 'equity (yi)',
    loan_total DOUBLE COMMENT 'loans (yi)',
    npl_ratio DOUBLE COMMENT 'NPL%',
    provision_coverage DOUBLE COMMENT 'provision coverage%',
    provision_ratio DOUBLE COMMENT 'loan provision ratio%',
    cap_adequacy_ratio DOUBLE COMMENT 'capital adequacy%',
    tier1_ratio DOUBLE COMMENT 'tier1 ratio%',
    nim DOUBLE COMMENT 'NIM%',
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_stock_date (stock_code, report_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='balance sheet + bank indicators';
"""

FINANCIAL_DIVIDEND_DDL = """
CREATE TABLE IF NOT EXISTS financial_dividend (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL,
    stock_name VARCHAR(50),
    ex_date DATE,
    record_date DATE,
    cash_div DOUBLE COMMENT 'div per share (pre-tax)',
    div_total DOUBLE COMMENT 'total div (yi)',
    div_ratio DOUBLE COMMENT 'payout ratio%',
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='dividend history';
"""

BANK_ASSET_QUALITY_DDL = """
CREATE TABLE IF NOT EXISTS bank_asset_quality (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    stock_code VARCHAR(10) NOT NULL,
    stock_name VARCHAR(50),
    report_date DATE NOT NULL,
    overdue_91 DOUBLE COMMENT 'overdue 91d+ loans (yi)',
    restructured DOUBLE COMMENT 'restructured loans (yi)',
    npl_ratio2 DOUBLE COMMENT 'custom NPL ratio 2%',
    provision_adj DOUBLE COMMENT 'provision adjustment (yi)',
    profit_adj_est DOUBLE COMMENT 'profit impact est (yi)',
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_stock_date (stock_code, report_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='bank asset quality (flitter method)';
"""

ALL_DDL = [
    FINANCIAL_INCOME_DDL,
    FINANCIAL_BALANCE_DDL,
    FINANCIAL_DIVIDEND_DDL,
    BANK_ASSET_QUALITY_DDL,
]
```

**Step 2: Commit**

```bash
git add data_analyst/financial_fetcher/schemas.py
git commit -m "feat(financial-fetcher): add DDL schemas for 4 financial tables"
```

---

### Task 3: Storage Layer

**Files:**
- Create: `data_analyst/financial_fetcher/storage.py`

**Step 1: Create `data_analyst/financial_fetcher/storage.py`**

Follow the same pattern as `strategist/log_bias/storage.py` - DDL execution, upsert with retry.

```python
# -*- coding: utf-8 -*-
"""storage layer for financial tables"""

import logging
import sys
import os
import time
from typing import Optional, List

import pandas as pd

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config.db import execute_query, get_connection
from .schemas import ALL_DDL

logger = logging.getLogger(__name__)


def _retry(func, desc: str, max_retries: int = 3, delay: int = 5):
    for attempt in range(1, max_retries + 1):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries:
                raise
            logger.warning(f"{desc} attempt {attempt} failed: {e}, retry in {delay}s")
            time.sleep(delay)


class FinancialStorage:
    """storage for financial tables"""

    def __init__(self, env: str = 'online'):
        self.env = env

    def init_tables(self):
        """create all tables if not exist"""
        def _do():
            conn = get_connection(self.env)
            cursor = conn.cursor()
            for ddl in ALL_DDL:
                cursor.execute(ddl)
            conn.commit()
            cursor.close()
            conn.close()
        _retry(_do, "init financial tables")
        logger.info("financial tables ready")

    def upsert(self, table: str, records: List[dict]) -> int:
        """
        generic upsert: INSERT ... ON DUPLICATE KEY UPDATE
        records must have all columns matching the table (excluding id, fetched_at)
        """
        if not records:
            return 0

        columns = list(records[0].keys())
        cols_sql = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))
        update_sql = ", ".join([f"{c} = VALUES({c})" for c in columns])

        sql = f"""
            INSERT INTO {table} ({cols_sql})
            VALUES ({placeholders})
            ON DUPLICATE KEY UPDATE {update_sql}
        """

        params_list = [tuple(r.get(c) for c in columns) for r in records]

        def _do():
            conn = get_connection(self.env)
            try:
                cursor = conn.cursor()
                cursor.executemany(sql, params_list)
                count = cursor.rowcount
                conn.commit()
                return count
            except Exception as e:
                conn.rollback()
                raise
            finally:
                cursor.close()
                conn.close()

        count = _retry(_do, f"upsert {len(records)} rows into {table}")
        logger.info(f"Upserted {count} rows into {table}")
        return count

    def query(self, sql: str, params: tuple = ()) -> List[dict]:
        """execute query and return list of dicts"""
        return execute_query(sql, params, env=self.env)
```

**Step 2: Smoke test**

Run: `cd /Users/zhaobo/data0/person/myTrader && DB_ENV=online python -c "from data_analyst.financial_fetcher.storage import FinancialStorage; s = FinancialStorage(); s.init_tables(); print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add data_analyst/financial_fetcher/storage.py
git commit -m "feat(financial-fetcher): add storage layer with DDL and upsert"
```

---

### Task 4: Core Fetcher (akshare)

**Files:**
- Create: `data_analyst/financial_fetcher/fetcher.py`

This is the biggest file. Adapted from example `fetcher.py`. Key changes:
- Replace sqlalchemy with FinancialStorage
- Keep akshare API calls as-is
- Add `safe_float()` utility

**Step 1: Create `data_analyst/financial_fetcher/fetcher.py`**

The full implementation is ~300 lines. Here is the complete code:

```python
# -*- coding: utf-8 -*-
"""financial data fetcher via akshare

Adapted from ~/Downloads/myTrader-example/fetcher.py
Replaced sqlalchemy with config.db, kept akshare API calls unchanged.
"""

import logging
import time
from datetime import datetime
from typing import List, Dict, Optional

import akshare as ak
import pandas as pd

_PROJECT_ROOT = "/Users/zhaobo/data0/person/myTrader"
import sys
import os
sys.path.insert(0, _PROJECT_ROOT)

from .storage import FinancialStorage
from .config import FinancialFetcherConfig

logger = logging.getLogger(__name__)


def safe_float(val, default=None):
    """safe float conversion, handle '--' and NaN"""
    try:
        if pd.isna(val) or str(val).strip() in ('--', '-', '', 'nan'):
            return default
        return float(str(val).replace('%', '').replace(',', ''))
    except Exception:
        return default


def _report_type(month: int) -> str:
    mapping = {3: "一季报", 6: "半年报", 9: "三季报", 12: "年报"}
    return mapping.get(month, "其他")


def fetch_income(stock_code: str, stock_name: str) -> List[dict]:
    """profit statement from akshare (east money)"""
    records = []
    try:
        df = ak.stock_profit_sheet_by_report_em(symbol=stock_code)
        if df is None or df.empty:
            return records

        for _, row in df.iterrows():
            raw = str(row.get("REPORT_DATE", ""))[:10]
            try:
                report_date = datetime.strptime(raw, "%Y-%m-%d").date()
            except Exception:
                continue

            revenue_raw = safe_float(row.get("TOTAL_OPERATE_INCOME"))
            net_profit_raw = safe_float(row.get("PARENT_NETPROFIT"))

            records.append({
                "stock_code": stock_code,
                "stock_name": stock_name,
                "report_date": report_date,
                "report_type": _report_type(report_date.month),
                "revenue": round(revenue_raw / 1e8, 4) if revenue_raw else None,
                "net_profit": round(net_profit_raw / 1e8, 4) if net_profit_raw else None,
                "net_profit_yoy": safe_float(row.get("PARENT_NETPROFIT_YOY")),
                "eps": safe_float(row.get("BASIC_EPS")),
                "roe": safe_float(row.get("WEIGHTAVG_ROE")),
                "gross_margin": safe_float(row.get("GROSS_PROFIT_RATIO")),
            })
    except Exception as e:
        logger.error(f"[{stock_code}] income fetch failed: {e}")
    return records


def fetch_balance(stock_code: str, stock_name: str) -> List[dict]:
    """balance sheet from akshare"""
    records = []
    try:
        df = ak.stock_balance_sheet_by_report_em(symbol=stock_code)
        if df is None or df.empty:
            return records

        for _, row in df.iterrows():
            raw = str(row.get("REPORT_DATE", ""))[:10]
            try:
                report_date = datetime.strptime(raw, "%Y-%m-%d").date()
            except Exception:
                continue

            total_assets_raw = safe_float(row.get("TOTAL_ASSETS"))
            total_equity_raw = safe_float(row.get("TOTAL_EQUITY"))

            records.append({
                "stock_code": stock_code,
                "stock_name": stock_name,
                "report_date": report_date,
                "total_assets": round(total_assets_raw / 1e8, 4) if total_assets_raw else None,
                "total_equity": round(total_equity_raw / 1e8, 4) if total_equity_raw else None,
                "loan_total": None,
                "npl_ratio": None,
                "provision_coverage": None,
                "provision_ratio": None,
                "cap_adequacy_ratio": None,
                "tier1_ratio": None,
                "nim": None,
            })
    except Exception as e:
        logger.error(f"[{stock_code}] balance fetch failed: {e}")
    return records


def fetch_bank_indicators(stock_code: str, stock_name: str) -> List[dict]:
    """bank-specific indicators: NPL, provision coverage, CAR, NIM"""
    records = []
    try:
        df = ak.stock_financial_analysis_indicator(symbol=stock_code, start_year="2018")
        if df is None or df.empty:
            return records

        for _, row in df.iterrows():
            raw = str(row.get("日期", ""))[:10]
            try:
                report_date = datetime.strptime(raw, "%Y-%m-%d").date()
            except Exception:
                continue

            records.append({
                "stock_code": stock_code,
                "stock_name": stock_name,
                "report_date": report_date,
                "npl_ratio": safe_float(row.get("不良贷款率(%)")),
                "provision_coverage": safe_float(row.get("拨备覆盖率(%)")),
                "provision_ratio": safe_float(row.get("贷款拨备率(%)")),
                "cap_adequacy_ratio": safe_float(row.get("资本充足率(%)")),
                "tier1_ratio": safe_float(row.get("一级资本充足率(%)")),
                "nim": safe_float(row.get("净息差(%)")),
            })
    except Exception as e:
        logger.warning(f"[{stock_code}] bank indicators failed (non-bank OK): {e}")
    return records


def fetch_dividend(stock_code: str, stock_name: str) -> List[dict]:
    """dividend history from akshare"""
    records = []
    try:
        df = ak.stock_history_dividend_detail(symbol=stock_code, indicator="分红")
        if df is None or df.empty:
            return records

        for _, row in df.iterrows():
            ex_date_raw = row.get("除权除息日") or row.get("ex_date", "")
            try:
                ex_date = datetime.strptime(str(ex_date_raw)[:10], "%Y-%m-%d").date()
            except Exception:
                ex_date = None

            cash_div = (
                safe_float(row.get("派息(税前)(元)"))
                or safe_float(row.get("每股股利(税前)"))
                or safe_float(row.get("现金分红(元/股)"))
            )

            records.append({
                "stock_code": stock_code,
                "stock_name": stock_name,
                "ex_date": ex_date,
                "record_date": None,
                "cash_div": cash_div,
                "div_total": None,
                "div_ratio": None,
            })
    except Exception as e:
        logger.error(f"[{stock_code}] dividend fetch failed: {e}")
    return records


def merge_bank_indicators(balance_records: List[dict], bank_records: List[dict]) -> List[dict]:
    """merge bank indicators into balance records by (stock_code, report_date)"""
    bank_map = {}
    for r in bank_records:
        key = (r["stock_code"], r["report_date"])
        bank_map[key] = r

    for rec in balance_records:
        key = (rec["stock_code"], rec["report_date"])
        if key in bank_map:
            bank = bank_map[key]
            rec["loan_total"] = rec.get("loan_total")
            rec["npl_ratio"] = bank.get("npl_ratio")
            rec["provision_coverage"] = bank.get("provision_coverage")
            rec["provision_ratio"] = bank.get("provision_ratio")
            rec["cap_adequacy_ratio"] = bank.get("cap_adequacy_ratio")
            rec["tier1_ratio"] = bank.get("tier1_ratio")
            rec["nim"] = bank.get("nim")
    return balance_records


def compute_provision_adj(storage: FinancialStorage, stock_code: str):
    """compute provision adjustment impact on profit (flitter method)"""
    rows = storage.query("""
        SELECT b.report_date,
               b.loan_total,
               b.provision_ratio,
               LAG(b.provision_ratio) OVER (PARTITION BY b.stock_code ORDER BY b.report_date) AS prev_ratio,
               LAG(b.loan_total) OVER (PARTITION BY b.stock_code ORDER BY b.report_date) AS prev_loan
        FROM financial_balance b
        WHERE b.stock_code = %s
        ORDER BY b.report_date
    """, (stock_code,))

    results = []
    for row in rows:
        if row["provision_ratio"] is None or row["prev_ratio"] is None:
            continue
        loan = row["loan_total"] or 0
        prev_loan = row["prev_loan"] or loan
        avg_loan = (loan + prev_loan) / 2

        ratio_change = (row["provision_ratio"] - row["prev_ratio"]) / 100
        provision_adj = ratio_change * avg_loan
        profit_adj_est = -provision_adj * 0.75

        results.append({
            "stock_code": stock_code,
            "stock_name": "",
            "report_date": row["report_date"],
            "provision_adj": round(provision_adj, 4),
            "profit_adj_est": round(profit_adj_est, 4),
        })
    logger.info(f"  [{stock_code}] provision adj: {len(results)} periods")
    return results


def run_fetch(config: FinancialFetcherConfig, stock_codes: Dict[str, str] = None,
              single_code: str = None) -> Dict[str, int]:
    """
    main entry: fetch all financial data for watch list

    Returns: {stock_code: records_saved_count}
    """
    targets = stock_codes or config.watch_list
    if single_code:
        targets = {single_code: targets.get(single_code, single_code)}

    storage = FinancialStorage(env=config.db_env)
    storage.init_tables()

    stats = {}
    for code, name in targets.items():
        logger.info(f"===== {name} ({code}) =====")
        total = 0

        # 1. income
        income = fetch_income(code, name)
        if income:
            storage.upsert("financial_income", income)
            total += len(income)
        logger.info(f"  income: {len(income)} rows")
        time.sleep(config.request_interval)

        # 2. balance
        balance = fetch_balance(code, name)
        time.sleep(config.request_interval)

        # 3. bank indicators (merge into balance)
        bank = fetch_bank_indicators(code, name)
        if bank:
            balance = merge_bank_indicators(balance, bank)
            logger.info(f"  bank indicators: {len(bank)} rows")
        if balance:
            storage.upsert("financial_balance", balance)
            total += len(balance)
        logger.info(f"  balance: {len(balance)} rows")
        time.sleep(config.request_interval)

        # 4. dividend
        div = fetch_dividend(code, name)
        if div:
            storage.upsert("financial_dividend", div)
            total += len(div)
        logger.info(f"  dividend: {len(div)} rows")
        time.sleep(config.request_interval)

        # 5. provision adjustment
        prov = compute_provision_adj(storage, code)
        if prov:
            storage.upsert("bank_asset_quality", prov)
            total += len(prov)

        stats[code] = total
        logger.info(f"===== {name} done: {total} rows =====\n")

    return stats
```

**Step 2: Smoke test (single stock)**

Run: `cd /Users/zhaobo/data0/person/myTrader && DB_ENV=online python -c "
from data_analyst.financial_fetcher.fetcher import run_fetch
from data_analyst.financial_fetcher.config import FinancialFetcherConfig
c = FinancialFetcherConfig()
stats = run_fetch(c, single_code='600015')
print(stats)
"`
Expected: processes 600015 (华夏银行), saves rows to 4 tables

**Step 3: Commit**

```bash
git add data_analyst/financial_fetcher/fetcher.py
git commit -m "feat(financial-fetcher): add akshare data fetcher for income/balance/dividend"
```

---

### Task 5: PDF Downloader (cninfo)

**Files:**
- Create: `data_analyst/financial_fetcher/cninfo_downloader.py`

Adapted from example `cninfo_downloader.py`. Mostly unchanged - it's standalone HTTP code.

**Step 1: Create `data_analyst/financial_fetcher/cninfo_downloader.py`**

Copy the full implementation from `~/Downloads/myTrader-example/cninfo_downloader.py` with these changes:
- Update `PDF_DIR` default to use `config.pdf_output_dir`
- Keep all functions as-is (search_announcements, download_pdf, batch_download, pdf_to_markdown_pymupdf, extract_key_sections)
- No emoji in log messages

This is ~200 lines, essentially a direct port. The implementer should copy the example file and make minimal adaptations.

**Step 2: Smoke test (search only, no download)**

Run: `cd /Users/zhaobo/data0/person/myTrader && python -c "
from data_analyst.financial_fetcher.cninfo_downloader import search_announcements
results = search_announcements('600015', '华夏银行', '年报', '2023-01-01')
for r in results[:3]:
    print(r['title'], r['date'], r['url'][:80])
print(f'Total: {len(results)}')
"`
Expected: prints found annual report entries

**Step 3: Commit**

```bash
git add data_analyst/financial_fetcher/cninfo_downloader.py
git commit -m "feat(financial-fetcher): add cninfo PDF annual report downloader"
```

---

### Task 6: Report Generator (Markdown)

**Files:**
- Create: `data_analyst/financial_fetcher/report_generator.py`

Adapted from example `fetcher.py` generate_markdown(). Key change: use FinancialStorage.query() instead of sqlalchemy engine.

**Step 1: Create `data_analyst/financial_fetcher/report_generator.py`**

Copy the `generate_markdown()` function from the example, adapting:
- Replace `engine.connect()` with `storage.query()`
- Remove emoji from direction indicators (use `[UP] conservative` / `[DOWN] releasing`)
- Output to `config.output_dir`

```python
# -*- coding: utf-8 -*-
"""generate Markdown financial summary"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from .storage import FinancialStorage

logger = logging.getLogger(__name__)


def generate_markdown(stock_code: str, stock_name: str,
                       storage: FinancialStorage,
                       output_dir: str) -> Optional[str]:
    """
    generate Markdown financial summary for a stock
    returns path to the generated file
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    lines = []
    lines.append("---")
    lines.append(f"tags: [financial, company/{stock_name}]")
    lines.append(f"stock_code: {stock_code}")
    lines.append(f"updated: {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("---")
    lines.append("")
    lines.append(f"# {stock_name} ({stock_code}) Financial Summary")
    lines.append("")

    # income
    lines.append("## Income Statement (Net Profit, yi)")
    lines.append("")
    rows = storage.query("""
        SELECT report_date, report_type, revenue, net_profit,
               net_profit_yoy, eps, roe
        FROM financial_income
        WHERE stock_code = %s
        ORDER BY report_date DESC LIMIT 16
    """, (stock_code,))

    if rows:
        lines.append("| Period | Type | Revenue(yi) | Net Profit(yi) | YoY% | EPS | ROE% |")
        lines.append("|--------|------|------------|---------------|------|-----|------|")
        for r in rows:
            lines.append(
                f"| {r['report_date']} | {r['report_type'] or '-'} "
                f"| {r['revenue'] or '-'} | {r['net_profit'] or '-'} "
                f"| {r['net_profit_yoy'] or '-'} | {r['eps'] or '-'} | {r['roe'] or '-'} |"
            )
    lines.append("")

    # bank indicators
    lines.append("## Bank Indicators")
    lines.append("")
    rows = storage.query("""
        SELECT report_date, npl_ratio, provision_coverage,
               provision_ratio, cap_adequacy_ratio, tier1_ratio, nim
        FROM financial_balance
        WHERE stock_code = %s AND npl_ratio IS NOT NULL
        ORDER BY report_date DESC LIMIT 12
    """, (stock_code,))

    if rows:
        lines.append("| Period | NPL% | ProvCov% | LoanProv% | CAR% | Tier1% | NIM% |")
        lines.append("|--------|------|---------|----------|------|--------|------|")
        for r in rows:
            lines.append(
                f"| {r['report_date']} | {r['npl_ratio'] or '-'} "
                f"| {r['provision_coverage'] or '-'} | {r['provision_ratio'] or '-'} "
                f"| {r['cap_adequacy_ratio'] or '-'} | {r['tier1_ratio'] or '-'} "
                f"| {r['nim'] or '-'} |"
            )
    lines.append("")

    # provision adjustment
    lines.append("## Provision Adjustment (flitter method)")
    lines.append("")
    lines.append("> Positive = conservative (hiding profit). Negative = releasing (beautifying profit).")
    lines.append("")
    rows = storage.query("""
        SELECT report_date, provision_adj, profit_adj_est
        FROM bank_asset_quality
        WHERE stock_code = %s
        ORDER BY report_date DESC LIMIT 8
    """, (stock_code,))

    if rows:
        lines.append("| Period | Prov Adj(yi) | Profit Impact(yi) | Direction |")
        lines.append("|--------|-------------|------------------|-----------|")
        for r in rows:
            if r["provision_adj"] is None:
                continue
            direction = "[UP] conservative" if r["provision_adj"] > 0 else "[DOWN] releasing"
            lines.append(
                f"| {r['report_date']} | {r['provision_adj']} "
                f"| {r['profit_adj_est']} | {direction} |"
            )
    lines.append("")

    # dividend
    lines.append("## Dividend History")
    lines.append("")
    rows = storage.query("""
        SELECT ex_date, cash_div, div_total, div_ratio
        FROM financial_dividend
        WHERE stock_code = %s
        ORDER BY ex_date DESC LIMIT 10
    """, (stock_code,))

    if rows:
        lines.append("| Ex-Date | Per Share(yi,pre-tax) | Total(yi) | Payout% |")
        lines.append("|--------|----------------------|----------|--------|")
        for r in rows:
            lines.append(
                f"| {r['ex_date'] or '-'} | {r['cash_div'] or '-'} "
                f"| {r['div_total'] or '-'} | {r['div_ratio'] or '-'} |"
            )
    lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append("- Source: akshare (east money API)")
    lines.append("- Units: amounts in yi, ratios in %")
    lines.append(f"- Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    content = "\n".join(lines)
    filename = f"{stock_name}_{stock_code}_financial_summary.md"
    filepath = output_path / filename
    filepath.write_text(content, encoding="utf-8")
    logger.info(f"Markdown saved: {filepath}")
    return str(filepath)
```

**Step 2: Smoke test**

Run: `cd /Users/zhaobo/data0/person/myTrader && DB_ENV=online python -c "
from data_analyst.financial_fetcher.report_generator import generate_markdown
from data_analyst.financial_fetcher.storage import FinancialStorage
s = FinancialStorage()
path = generate_markdown('600015', '华夏银行', s, '/tmp/fin_test')
print(path)
"`
Expected: prints path to generated Markdown file

**Step 3: Commit**

```bash
git add data_analyst/financial_fetcher/report_generator.py
git commit -m "feat(financial-fetcher): add Markdown report generator"
```

---

### Task 7: RAG Ingest (ChromaDB)

**Files:**
- Create: `data_analyst/financial_fetcher/rag_ingest.py`

Adapted from example `rag_ingest.py`. Key changes:
- Replace Qdrant with ChromaDB (via investment_rag)
- Replace BGE-M3 with DashScope EmbeddingClient (via investment_rag)

**Step 1: Create `data_analyst/financial_fetcher/rag_ingest.py`**

```python
# -*- coding: utf-8 -*-
"""ingest financial data into ChromaDB

Reuses investment_rag's ChromaClient and EmbeddingClient.
"""

import hashlib
import logging
import re
import time
from pathlib import Path
from typing import List

_PROJECT_ROOT = "/Users/zhaobo/data0/person/myTrader"
import sys
sys.path.insert(0, _PROJECT_ROOT)

from investment_rag.store.chroma_client import ChromaClient
from investment_rag.embeddings.embed_model import EmbeddingClient
from investment_rag.config import DEFAULT_CONFIG

logger = logging.getLogger(__name__)


def _split_markdown(md_text: str, chunk_size: int = 800, overlap: int = 150) -> List[str]:
    """split markdown by ## sections, then sliding window for long sections"""
    chunks = []
    sections = re.split(r'\n(?=## )', md_text)

    for section in sections:
        if not section.strip():
            continue
        if len(section) <= chunk_size:
            chunks.append(section.strip())
        else:
            # sliding window
            start = 0
            while start < len(section):
                end = start + chunk_size
                if end < len(section):
                    for sep in ['\n', '。', '；']:
                        idx = section.rfind(sep, start + chunk_size // 2, end)
                        if idx != -1:
                            end = idx + 1
                            break
                chunk = section[start:end].strip()
                if chunk:
                    chunks.append(chunk)
                start = end - overlap
                if start >= len(section):
                    break
    return chunks


def ingest_markdown_files(md_dir: str, collection: str = "financials",
                          embed_client: EmbeddingClient = None,
                          chroma_client: ChromaClient = None) -> int:
    """
    batch ingest Markdown financial summaries into ChromaDB
    returns total chunks ingested
    """
    embed = embed_client or EmbeddingClient(DEFAULT_CONFIG)
    chroma = chroma_client or ChromaClient(DEFAULT_CONFIG)
    col = chroma.get_collection(collection)

    md_files = list(Path(md_dir).glob("*_financial_summary.md"))
    logger.info(f"Found {len(md_files)} financial summary files")

    total = 0
    for md_path in md_files:
        # parse stock info from filename: {name}_{code}_financial_summary.md
        parts = md_path.stem.split("_")
        if len(parts) < 2:
            continue
        stock_name = parts[0]
        stock_code = parts[1]

        logger.info(f"  Processing: {md_path.name}")
        text = md_path.read_text(encoding="utf-8")
        chunks = _split_markdown(text)

        if not chunks:
            continue

        # embed
        embeddings = embed.embed_texts(chunks)

        # prepare ids and metadatas
        ids = []
        metadatas = []
        for i, chunk_text in enumerate(chunks):
            id_str = f"fin_{stock_code}_{md_path.name}_{i}"
            chunk_id = int(hashlib.md5(id_str.encode()).hexdigest()[:8], 16)
            ids.append(str(chunk_id))
            metadatas.append({
                "stock_code": stock_code,
                "stock_name": stock_name,
                "source": md_path.name,
                "data_type": "financial_summary",
                "chunk_idx": i,
            })

        col.add(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas)
        total += len(chunks)
        logger.info(f"  [{stock_code}] ingested {len(chunks)} chunks")
        time.sleep(0.3)

    logger.info(f"Total ingested: {total} chunks")
    return total


def ingest_pdf_text(pdf_path: str, stock_code: str, stock_name: str,
                     report_year: str, collection: str = "financials",
                     embed_client: EmbeddingClient = None,
                     chroma_client: ChromaClient = None) -> int:
    """ingest a single PDF's extracted text into ChromaDB"""
    from .cninfo_downloader import pdf_to_markdown_pymupdf

    embed = embed_client or EmbeddingClient(DEFAULT_CONFIG)
    chroma = chroma_client or ChromaClient(DEFAULT_CONFIG)
    col = chroma.get_collection(collection)

    full_text = pdf_to_markdown_pymupdf(Path(pdf_path))
    if not full_text:
        logger.warning(f"PDF text extraction failed: {pdf_path}")
        return 0

    # split by page markers
    pages = re.split(r'<!-- page (\d+) -->', full_text)
    chunks = []
    current_text = ""
    current_pages = []

    for i, part in enumerate(pages):
        if part.isdigit():
            continue
        current_text += part
        if len(current_text) >= 800:
            chunks.append(current_text.strip()[:1000])
            current_text = current_text[-150:]
        current_pages.append(i)

    if current_text.strip():
        chunks.append(current_text.strip()[:1000])

    if not chunks:
        return 0

    embeddings = embed.embed_texts(chunks)
    ids = []
    metadatas = []
    for i, chunk_text in enumerate(chunks):
        id_str = f"fin_pdf_{stock_code}_{report_year}_{i}"
        chunk_id = int(hashlib.md5(id_str.encode()).hexdigest()[:8], 16)
        ids.append(str(chunk_id))
        metadatas.append({
            "stock_code": stock_code,
            "stock_name": stock_name,
            "source": Path(pdf_path).name,
            "data_type": "pdf_annual_report",
            "report_year": report_year,
            "chunk_idx": i,
        })

    col.add(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas)
    logger.info(f"  [{stock_code}] PDF ingested {len(chunks)} chunks")
    return len(chunks)
```

**Step 2: Commit**

```bash
git add data_analyst/financial_fetcher/rag_ingest.py
git commit -m "feat(financial-fetcher): add ChromaDB RAG ingest (reuse investment_rag)"
```

---

### Task 8: CLI Entry Point

**Files:**
- Create: `data_analyst/financial_fetcher/run_fetcher.py`

**Step 1: Create `data_analyst/financial_fetcher/run_fetcher.py`**

```python
# -*- coding: utf-8 -*-
"""CLI entry point for financial fetcher"""

import argparse
import logging
import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from .config import FinancialFetcherConfig
from .fetcher import run_fetch
from .storage import FinancialStorage
from .report_generator import generate_markdown
from .cninfo_downloader import batch_download
from .rag_ingest import ingest_markdown_files

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger('financial_fetcher')


def main():
    parser = argparse.ArgumentParser(description='Financial Data Fetcher')
    parser.add_argument('--code', type=str, help='Single stock code to fetch')
    parser.add_argument('--env', type=str, default='online', choices=['local', 'online'])
    parser.add_argument('--output', type=str, help='Output dir for Markdown')
    parser.add_argument('--download-pdf', action='store_true', help='Download PDF annual reports')
    parser.add_argument('--ingest-rag', action='store_true', help='Ingest Markdown to ChromaDB')
    parser.add_argument('--no-db', action='store_true', help='Skip database writes')

    args = parser.parse_args()
    config = FinancialFetcherConfig()
    if args.env:
        config.db_env = args.env
    if args.output:
        config.output_dir = args.output

    try:
        # 1. fetch structured data
        if not args.no_db:
            stats = run_fetch(config, single_code=args.code)
            logger.info(f"Fetch stats: {stats}")

        # 2. generate markdown
        storage = FinancialStorage(env=config.db_env)
        targets = {args.code: config.watch_list.get(args.code, args.code)} if args.code else config.watch_list
        for code, name in targets.items():
            path = generate_markdown(code, name, storage, config.output_dir)
            if path:
                logger.info(f"Report: {path}")

        # 3. download PDF
        if args.download_pdf:
            paths = batch_download(
                targets,
                ann_types=["年报"],
                start_year=2023,
            )
            logger.info(f"PDF downloaded: {len(paths)}")

        # 4. RAG ingest
        if args.ingest_rag:
            count = ingest_markdown_files(config.output_dir)
            logger.info(f"RAG ingested: {count} chunks")

        logger.info("Done")

    except Exception as e:
        logger.error(f"Fatal: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
```

**Step 2: Commit**

```bash
git add data_analyst/financial_fetcher/run_fetcher.py
git commit -m "feat(financial-fetcher): add CLI entry point run_fetcher"
```

---

### Task 9: End-to-End Verification

**Step 1: Run full pipeline for single stock**

```bash
cd /Users/zhaobo/data0/person/myTrader && DB_ENV=online python -m data_analyst.financial_fetcher.run_fetcher --code 600015 --ingest-rag
```

Expected: fetches 600015 data, generates Markdown, ingests to ChromaDB.

**Step 2: Verify data in MySQL**

```bash
DB_ENV=online python -c "
from config.db import execute_query
for t in ['financial_income', 'financial_balance', 'financial_dividend', 'bank_asset_quality']:
    rows = execute_query(f'SELECT COUNT(*) as cnt FROM {t} WHERE stock_code=%s', ('600015',))
    print(f'{t}: {rows[0][\"cnt\"]} rows')
"
```

**Step 3: Verify ChromaDB**

```bash
python -c "
from investment_rag.store.chroma_client import ChromaClient
from investment_rag.config import DEFAULT_CONFIG
c = ChromaClient(DEFAULT_CONFIG)
col = c.get_collection('financials')
print(f'financials collection: {col.count()} documents')
"
```

**Step 4: Commit any fixes, final commit**

```bash
git add -A && git commit -m "feat(financial-fetcher): end-to-end verification complete"
```

---

## Summary

| Task | File | Description |
|------|------|-------------|
| 1 | config.py, __init__.py | Package + config (watch list, paths) |
| 2 | schemas.py | DDL for 4 tables |
| 3 | storage.py | MySQL init + generic upsert |
| 4 | fetcher.py | akshare income/balance/bank/dividend |
| 5 | cninfo_downloader.py | cninfo PDF download |
| 6 | report_generator.py | Markdown financial summary |
| 7 | rag_ingest.py | ChromaDB ingest (reuse investment_rag) |
| 8 | run_fetcher.py | CLI entry (argparse) |
| 9 | verification | E2E test + DB + ChromaDB check |
