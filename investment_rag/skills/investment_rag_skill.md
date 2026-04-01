# Investment RAG Query Skill

## Description
Query the A-share investment research RAG system to find relevant research reports, sector analysis, and structured financial data.

## Instructions
Use this skill when the user asks questions about A-share investment research, sector analysis, company research, or financial metrics that may be answered by searching through the ingested research documents and database.

## Usage

### Query the RAG system
```
/investment-rag <query>
```

### Examples
- `/investment-rag 化工新材料行业的发展趋势和投资机会`
- `/investment-rag 煤炭行业2026年前景分析`
- `/investment-rag PE小于20且PB小于1的股票筛选`
- `/investment-rag 核电行业投资机会`

## How to use
When the user invokes this skill with a query:

1. Start the RAG API server if not already running:
   ```bash
   python3 -m investment_rag.api.main &
   ```

2. Send the query to the API:
   ```bash
   curl -s -X POST http://localhost:8900/query \
     -H "Content-Type: application/json" \
     -d '{"query": "<user query>", "top_k": 5}' | python3 -m json.tool
   ```

3. Analyze the results and provide a concise summary to the user, including:
   - Which documents were found relevant
   - Key excerpts from the top results
   - Source attribution (file name, page)

### Intent detection
The system automatically routes queries:
- **RAG**: Semantic/analytical queries -> searches ChromaDB + BM25
- **SQL**: Structured data queries (e.g., "PE<20") -> queries MySQL
- **Hybrid**: Combined queries -> SQL first, then RAG

## Collections
- `reports`: Sell-side research reports (default)
- `announcements`: Company announcements
- `notes`: Personal research notes
- `macro`: Macro policy and economic data

## Ingest new documents
```bash
python3 -m investment_rag.run_pipeline --file path/to/report.pdf --collection reports
python3 -m investment_rag.run_pipeline --dir ~/Documents/notes/Finance/Research --collection reports
python3 -m investment_rag.run_pipeline --all
```
