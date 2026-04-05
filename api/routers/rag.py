# -*- coding: utf-8 -*-
"""
RAG router - SSE streaming RAG query
"""
import json
import logging

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse

from api.middleware.auth import get_current_user
from api.models.user import User
from api.schemas.rag import RAGQueryRequest, RAGQueryResponse

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/rag', tags=['rag'])


@router.post('/query')
async def rag_query(
    req: RAGQueryRequest,
    current_user: User = Depends(get_current_user),
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
    current_user: User = Depends(get_current_user),
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
