# -*- coding: utf-8 -*-
"""
RAG router - SSE streaming RAG query
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from api.schemas.rag import (
    RAGQueryRequest,
    RAGQueryResponse,
    ReportGenerateRequest,
    ReportListItem,
    ReportListResponse,
)

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/rag', tags=['rag'])


@router.post('/query')
async def rag_query(
    req: RAGQueryRequest,
):
    """
    Query the RAG system with SSE streaming response.
    Returns answer token by token, followed by source references.
    """
    try:
        from investment_rag.retrieval.intent_router import IntentRouter
        from investment_rag.retrieval.hybrid_retriever import HybridRetriever
        from investment_rag.retrieval.reranker import Reranker
        from investment_rag.retrieval.text2sql import Text2SQL
    except ImportError as e:
        logger.error('[RAG] Import error: %s', e)
        raise HTTPException(
            status_code=503,
            detail=f'RAG module not available: {str(e)}',
        )

    async def event_generator():
        try:
            # 1. Route intent
            intent_router = IntentRouter()
            route = intent_router.route(req.query)
            intent = route.intent
            collection = req.collection or route.collection

            yield f"data: {json.dumps({'type': 'intent', 'intent': intent, 'collection': collection})}\n\n"

            sql_results = None

            # 2. Handle SQL intent
            if intent == 'sql':
                t2s = Text2SQL()
                sql_results = t2s.execute(req.query)
                yield f"data: {json.dumps({'type': 'sql', 'results': sql_results}, default=str)}\n\n"

                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            # 3. Handle hybrid (SQL + RAG)
            if intent == 'hybrid':
                t2s = Text2SQL()
                sql_results = t2s.execute(req.query)
                yield f"data: {json.dumps({'type': 'sql', 'results': sql_results}, default=str)}\n\n"

            # 4. RAG retrieval
            retriever = HybridRetriever()
            hits = retriever.retrieve(
                query=req.query,
                collection=collection,
                top_k=req.top_k,
            )

            # 5. Rerank
            reranker = Reranker()
            hits = reranker.rerank(req.query, hits, top_k=req.top_k)

            # 6. Send sources
            sources = []
            for h in hits[:req.top_k]:
                src = {
                    'source': h.get('metadata', {}).get('source', ''),
                    'text': h['text'][:200] + '...' if len(h.get('text', '')) > 200 else h.get('text', ''),
                    'score': h.get('rerank_score', h.get('rrf_score', 0.0)),
                    'metadata': h.get('metadata', {}),
                }
                sources.append(src)

            yield f"data: {json.dumps({'type': 'sources', 'sources': sources}, ensure_ascii=False)}\n\n"

            # 7. Generate answer with LLM streaming
            try:
                from openai import OpenAI

                context_text = '\n\n'.join([
                    f"[{s['source']}]: {h['text']}" for s, h in zip(sources, hits[:req.top_k])
                ])

                prompt = f"""Based on the following research context, answer the user's question.
If the context doesn't contain relevant information, say so.

Context:
{context_text}

Question: {req.query}

Answer:"""

                client = OpenAI(
                    api_key=None,  # Will use env variable
                    base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
                )
                stream = client.chat.completions.create(
                    model='qwen3-max',
                    messages=[{'role': 'user', 'content': prompt}],
                    stream=True,
                )

                full_answer = ''
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        token = chunk.choices[0].delta.content
                        full_answer += token
                        yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"

                yield f"data: {json.dumps({'type': 'done', 'answer': full_answer}, ensure_ascii=False)}\n\n"

            except Exception as e:
                logger.error('[RAG] LLM streaming error: %s', e)
                no_context_msg = "Unable to generate answer from LLM. Please check RAG configuration."
                yield f"data: {json.dumps({'type': 'done', 'answer': no_context_msg})}\n\n"

        except Exception as e:
            logger.error('[RAG] Query error: %s', e)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )


@router.post('/query/sync', response_model=RAGQueryResponse)
async def rag_query_sync(
    req: RAGQueryRequest,
):
    """
    Non-streaming RAG query. Returns complete response.
    Useful for API Key / programmatic access.
    """
    try:
        from investment_rag.retrieval.intent_router import IntentRouter
        from investment_rag.retrieval.hybrid_retriever import HybridRetriever
        from investment_rag.retrieval.reranker import Reranker
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f'RAG module not available: {str(e)}')

    intent_router = IntentRouter()
    route = intent_router.route(req.query)
    collection = req.collection or route.collection

    sql_results = None
    rag_results = []

    if route.intent == 'sql':
        from investment_rag.retrieval.text2sql import Text2SQL
        t2s = Text2SQL()
        sql_results = t2s.execute(req.query)
    else:
        if route.intent == 'hybrid':
            from investment_rag.retrieval.text2sql import Text2SQL
            t2s = Text2SQL()
            sql_results = t2s.execute(req.query)

        retriever = HybridRetriever()
        hits = retriever.retrieve(query=req.query, collection=collection, top_k=req.top_k)
        reranker = Reranker()
        hits = reranker.rerank(req.query, hits, top_k=req.top_k)

        rag_results = [
            {
                'source': h.get('metadata', {}).get('source', ''),
                'text': h['text'],
                'score': h.get('rerank_score', h.get('rrf_score', 0.0)),
                'metadata': h.get('metadata', {}),
            }
            for h in hits
        ]

    return RAGQueryResponse(
        query=req.query,
        intent=route.intent,
        answer='',
        sources=rag_results,
        sql_results=sql_results,
    )


@router.post('/report/generate')
async def report_generate(
    req: ReportGenerateRequest,
):
    """
    SSE 流式生成智能研报。

    SSE event types:
      {type: "plan",       sections: [...]}
      {type: "step_start", step: "step1", name: "信息差"}
      {type: "step_done",  step: "step1", name: "信息差", content: "..."}
      {type: "done",       report_id: "...", content: "..."}
      {type: "error",      message: "..."}
    """
    async def event_generator():
        try:
            from investment_rag.report_engine.five_step import FiveStepAnalyzer
            from investment_rag.report_engine.report_builder import ReportBuilder
            from investment_rag.report_engine.report_store import ReportStore
            from investment_rag.report_engine.prompts import FIVE_STEP_CONFIG
        except ImportError as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Module unavailable: {exc}'})}\n\n"
            return

        # 1. Plan
        sections = []
        if req.report_type in ('fundamental', 'comprehensive'):
            sections.extend([c.name for c in FIVE_STEP_CONFIG])
        if req.report_type in ('technical', 'comprehensive'):
            sections.append('技术面')

        yield f"data: {json.dumps({'type': 'plan', 'sections': sections}, ensure_ascii=False)}\n\n"

        analyzer = FiveStepAnalyzer(db_env='online')
        builder = ReportBuilder()
        store = ReportStore()
        fundamental_results = {}
        tech_section = ''

        # 2. Fundamental steps (step1..step5) - v2.0: 摘要式上下文传递
        executive_summary = ''
        if req.report_type in ('fundamental', 'comprehensive'):
            step_outputs = {}
            for step_config in FIVE_STEP_CONFIG:
                yield f"data: {json.dumps({'type': 'step_start', 'step': step_config.step_id, 'name': step_config.name}, ensure_ascii=False)}\n\n"

                prev_summary = analyzer._build_prev_summary(step_config.step_id, step_outputs)
                step_result = analyzer._run_single_step(
                    step_config=step_config,
                    stock_code=req.stock_code,
                    stock_name=req.stock_name,
                    prev_analysis=prev_summary,
                    collection=req.collection,
                )
                fundamental_results[step_config.step_id] = step_result
                step_outputs[step_config.step_id] = step_result

                yield f"data: {json.dumps({'type': 'step_done', 'step': step_config.step_id, 'name': step_config.name, 'content': step_result}, ensure_ascii=False)}\n\n"

            # Generate executive summary
            full_report_text = '\n\n---\n\n'.join(
                fundamental_results.get(sc.step_id, '') for sc in FIVE_STEP_CONFIG
            )
            executive_summary = analyzer._generate_executive_summary(
                stock_code=req.stock_code,
                stock_name=req.stock_name,
                full_analysis=full_report_text,
                system_prompt='',
            )

        # 3. Technical section
        if req.report_type in ('technical', 'comprehensive'):
            yield f"data: {json.dumps({'type': 'step_start', 'step': 'tech', 'name': '技术面'}, ensure_ascii=False)}\n\n"
            tech_section = analyzer.generate_tech_section(req.stock_code, req.stock_name)
            yield f"data: {json.dumps({'type': 'step_done', 'step': 'tech', 'name': '技术面', 'content': tech_section}, ensure_ascii=False)}\n\n"

        # 4. Assemble
        if req.report_type == 'comprehensive':
            final_report = builder.build_comprehensive(
                stock_code=req.stock_code,
                stock_name=req.stock_name,
                fundamental_results=fundamental_results,
                tech_section=tech_section,
                executive_summary=executive_summary,
            )
        elif req.report_type == 'fundamental':
            final_report = builder.build_fundamental_only(
                stock_code=req.stock_code,
                stock_name=req.stock_name,
                fundamental_results=fundamental_results,
                executive_summary=executive_summary,
            )
        else:  # technical
            final_report = f"# {req.stock_name}（{req.stock_code}）技术面分析\n\n{tech_section}"

        report_id = store.save(
            stock_code=req.stock_code,
            stock_name=req.stock_name,
            report_type=req.report_type,
            content=final_report,
        )

        yield f"data: {json.dumps({'type': 'done', 'report_id': report_id, 'content': final_report}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )


@router.get('/report/list', response_model=ReportListResponse)
async def report_list(
    stock_code: Optional[str] = None,
    limit: int = 20,
):
    """列举已保存研报（按创建时间倒序）"""
    from investment_rag.report_engine.report_store import ReportStore
    store = ReportStore()
    reports = store.list_reports(stock_code=stock_code, limit=limit)
    items = [ReportListItem(**r) for r in reports]
    return ReportListResponse(reports=items, total=len(items))


@router.get('/report/{report_id}')
async def report_get(
    report_id: str,
):
    """获取研报 Markdown 内容（Content-Type: text/markdown）"""
    from investment_rag.report_engine.report_store import ReportStore
    from fastapi.responses import PlainTextResponse
    store = ReportStore()
    content = store.get(report_id)
    if content is None:
        raise HTTPException(status_code=404, detail='Report not found')
    return PlainTextResponse(content=content, media_type='text/markdown; charset=utf-8')
