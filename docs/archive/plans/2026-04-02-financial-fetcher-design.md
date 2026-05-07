# Financial Fetcher Design

> Based on example code in ~/Downloads/myTrader-example/ and technical spec in ~/Documents/notes/

## Scope

Full pipeline: structured data (akshare) + PDF download (cninfo) + RAG ingest (ChromaDB)

## Architecture

Module: `data_analyst/financial_fetcher/`
DB: online MySQL (via config.db)
Vector store: ChromaDB (reuse investment_rag)
Embedding: DashScope text-embedding-v4 (reuse investment_rag)

## Data Flow

```
akshare API -> fetcher.py -> MySQL (4 tables)
cninfo.com.cn -> cninfo_downloader.py -> PDF files
                                         |
                              report_generator.py -> Markdown summary
                                         |
                              rag_ingest.py -> ChromaDB collection "financials"
```

## MySQL Tables

- `financial_income` - profit statement (revenue, net_profit, roe, eps, yoy)
- `financial_balance` - balance sheet + bank indicators (npl_ratio, provision_coverage, cap_adequacy, nim)
- `financial_dividend` - dividend history
- `bank_asset_quality` - NPL ratio 2 (reserved for PDF extraction)

## Module Structure

```
data_analyst/financial_fetcher/
  __init__.py
  config.py              # watch list, thresholds, output paths
  schemas.py             # DDL + Pydantic models
  fetcher.py             # akshare data fetching
  cninfo_downloader.py   # cninfo PDF download
  storage.py             # MySQL CRUD (reuse config.db)
  report_generator.py    # Markdown financial summary
  rag_ingest.py          # Markdown/PDF -> ChromaDB (reuse investment_rag)
  run_fetcher.py         # CLI entry
```

## RAG Integration

- New ChromaDB collection: "financials"
- Reuse EmbeddingClient (DashScope) and ChromaClient from investment_rag
- Markdown chunks by ## sections, metadata: stock_code, report_type, section
- PDF chunks by page, metadata: stock_code, report_year, page_range

## Scheduler

- Daily 07:00: structured data update
- Weekly Sat 09:00: PDF annual report check

## CLI

```bash
python -m data_analyst.financial_fetcher.run_fetcher
python -m data_analyst.financial_fetcher.run_fetcher --code 600015
python -m data_analyst.financial_fetcher.run_fetcher --download-pdf
python -m data_analyst.financial_fetcher.run_fetcher --ingest-rag
```

## Key Differences from Example Code

| Aspect | Example | Adapted |
|--------|---------|---------|
| DB | sqlalchemy | config.db (pymysql) |
| Vector | Qdrant | ChromaDB (reuse) |
| Embedding | BGE-M3 local | DashScope API (reuse) |
| Watch list | hardcoded | config.py dataclass |
| Markdown output | Obsidian symlink | configurable output_dir |
