# 投研 RAG 系统

# 技术方案 & 任务拆分

v1.0 · 2026-04 · 个人投研系统 对外付费 → SaaS

# 1. 目标定义

本系统面向 A 股个人投资者，将研报、公告、量化因子、个人笔记统一纳入检索范围，通过自然语言交互实现投研知识的即时获取，最终开放为付费 SaaS 服务。

<table><tr><td>核心场景</td><td>研报语义检索、公告问答、量化因子查询（Text2SQL）、个人笔记检索</td></tr><tr><td>当前入口</td><td>Claude Skill（本地快速验证），后续扩展 FastAPI + Web UI</td></tr><tr><td>差异化</td><td>结构化因子库（myTrader）+非结构化研报联合查询，市面上尚无成熟产品</td></tr><tr><td>目标用户</td><td>个人投资者、小型私募研究员，愿意为专业信息检索付费</td></tr><tr><td>商业化方向</td><td>Token包/月订阅，早期内测10-20人验证PMF</td></tr></table>

# 2. 整体架构

![image](https://cdn-mineru.openxlab.org.cn/result/2026-04-01/e39494b4-961f-4800-8654-2a55a1cc1568/3e027fe67b1df484c363848d5d54d06d423330e08a64d6e4bfc6e9d87027ab4a.jpg)


![image](https://cdn-mineru.openxlab.org.cn/result/2026-04-01/e39494b4-961f-4800-8654-2a55a1cc1568/83c05cef4ddd7d7f38ecdfffcd274df2d5517a2fb47dfbf74bdb47003ae5c6b1.jpg)


# 3. 技术选型

# 3.1 核心组件

<table><tr><td>模块</td><td>选型</td><td>理由</td></tr><tr><td>Embedding 模型</td><td>BGE-M3（本地）/ text-embedding-v4（API 备用）</td><td>中英文金融文本最佳，支持 8192 tokens 长文档，混合检索(dense+sparse)</td></tr><tr><td>向量数据库</td><td>Qdrant（Docker 本地 + 云端同一镜像）</td><td>Rust 开发内存效率高，过滤查询强，适合 ticker/date 复合过滤</td></tr><tr><td>Reranker</td><td>bge-reranker-v2-m3</td><td>BAAI 出品，与 BGE-M3 配套，中文效果好</td></tr><tr><td>LLM</td><td>DeepSeek-V3（API）</td><td>中文财报理解强，成本比 GPT-4 低 90%+</td></tr><tr><td>框架</td><td>LangChain（最小化使用，仅做工具封装）</td><td>避免过度抽象，核心逻辑自己写，LangChain 只做 PDF loader 等工具层</td></tr><tr><td>PDF 解析</td><td>MinerU（复杂表格）+PyMuPDF（普通文本）</td><td>MinerU 表格提取准确率高，是你现在用的工具</td></tr><tr><td>API 服务</td><td>FastAPI</td><td>已有技术栈</td></tr><tr><td>调度</td><td>APScheduler</td><td>轻量，适合单机定时爬取</td></tr><tr><td>本地 DB</td><td>MySQL（复用 myTrader）</td><td>行情/因子/财务数据已在库中，直接复用</td></tr><tr><td>缓存</td><td>Redis</td><td>Query embedding 缓存，避免重复调用 Embedding 模型</td></tr></table>

# 3.2 Embedding 策略

金融文档的 Embedding 有两点特殊要求：

专业术语密集（"EBITDA""商誉减值""净敞口"），需要模型具备金融语义理解能力

• 中英文混合（财报、研报大量中英文混排），单语言模型效果下降显著

• 长文档（年报普遍 100-200 页），需要支持 $4 0 9 6 +$ tokens 的上下文窗口

投资分析报告场景：使用BGE-M3dense向量，维度1024，max_length=8192。文档中提到的 Jina-embedding 2048维方案性能更好但内存占用翻倍， 作为后期升级选项。

# 4. 项目目录结构

```txt
investment_rag/  
- ingest/ # 数据摄入  
- crawlers/ # 公告爬虫  
- cninfo crawler.py # 研报爬虫  
- report crawler.py # MinerU/PyMuPDF  
- parsers/ # Obsidian笔记解析  
- pdf_parser.py # MinerU/PyMuPDF  
- md_parser.py # Obsidian笔记解析  
- loaders/ #行情/财务数据  
- akshareloader.py # 定时任务  
embeddings/ # BGE-M3 封装  
- embed_model.py # 批量 embedding 脚本  
- batch_embedding.py # Qdrant 操作封装  
- qdrant_client.py # MySQL 封装(复用 myTrader)  
- mysql_client.py # MySQL 版本  
- retrieval/ # 意图路由  
- intent_ROUTer.py # 查询改写  
- query_rewriter.py # BGE-M3 + BM25  
- hybrid_retriever.py # Cross-encoder  
- reranker.py # 复用 Feishu bot 模块  
- text2sql.py # 复用 Feishu bot 模块  
- generation/ # per query type prompts  
- llm_client.py # DeepSeek-V3 封装  
- api/ # FastAPI 入口  
- main.py # Claude Skill 入口  
- schemas.py #Claude Skill 入口  
- investment_rag}skill.md  
tests/ #黄金测试集  
- golden_set.json # Qdrant + Redis  
- docker-compose.yml # Qdrant + Redis  
- config.py
```

# 5. 数据层设计

# 5.1 Qdrant Collections

按数据类型分 4 个独立 Collection，支持跨 Collection 联合检索：

<table><tr><td>Collection</td><td>数据来源</td><td>关键 Payload 字段</td></tr><tr><td>reports</td><td>东方财富/同花顺研报 PDF（公开）</td><td>ticket, date, analyst, broker, rating, page, chunk_id</td></tr><tr><td>announcements</td><td>cninfo 公告（年报/季报/重大事项）</td><td>ticket, date, ann_type, page, chunk_id</td></tr><tr><td>notes</td><td>Obsidian Vault MD 文件</td><td>file_name, created_at, tags, folder</td></tr><tr><td>macro</td><td>宏观政策文本/CFTC/PPI 发布等</td><td>source, date, category</td></tr></table>

from qdrant_client import QdrantClient   
from qdrant_client.models import VectorParams,Distance, PayloadSchemaType   
client $=$ QdrantClient("localhost",port $\coloneqq$ 6333)   
COLLECTIONS $=$ { "reports": {"desc":"卖方研报"}, "announcements": {"desc":"上市公司公告"}, "notes": {"desc":"Obsidian个人笔记"}, "macro": {"desc":"宏观数据/政策文本"},   
}   
for name in COLLECTIONS: client.recreate.collection( collection_name $\equiv$ name, vectors_config=VectorParams(size $\coloneqq$ 1024,distance $\coloneqq$ Distance.COSINE), #Metadata payload: ticker, date, source, page, chunk_id   
#Payload schema for filtering client.create_payload_index("reports","ticket",PayloadSchemaType(KEYWORD) client.create_payload_index("reports","date",PayloadSchemaType.DATETIME) client.create_payload_index("reports","report_type",PayloadSchemaType(KEYWORD)

# 5.2 MySQL 复用策略

直接复用 myTrader 的 MySQL 连接，Text2SQL 查询目标：

• stock_daily_factor：已入库的 7 个基础因子 $^ +$ 宏观因子（oil_mom_20 等）

financial_data：营收/净利润/毛利率等财务指标（需要补充入库 akshare 财务数据）

stock_price：日行情数据

关键行动项：用akshare的stock_financial_report_sina接口补充财务报表数据入MySQL，这是Text2SQL 分支查询财务指标的基础。

# 6. 检索管道设计

# 6.1 意图路由

所有查询先经过意图路由，决定走 Text2SQL 还是语义 RAG：

<table><tr><td>查询类型</td><td>示例</td><td>路由目标</td></tr><tr><td>结构化数值查询</td><td>&quot;茅台2024年毛利率多少&quot;&quot;中矿资源最近PE&quot;</td><td>Text2SQL → MySQL</td></tr><tr><td>因子筛选</td><td>&quot;PB&lt;1且近30天涨幅&gt;10%的煤炭股&quot;</td><td>Text2SQL → MySQL</td></tr><tr><td>语义/分析类</td><td>&quot;机构对中芯国际的看法&quot;&quot;煤化工板块风险点&quot;</td><td>Hybrid RAG → Qdrant</td></tr><tr><td>笔记检索</td><td>&quot;我对Hormuz的分析&quot;&quot;我的煤化工笔记&quot;</td><td>RAG → notes collection</td></tr><tr><td>混合查询</td><td>&quot;营收增速&gt;20%的科技公司，找相关研报&quot;</td><td>先Text2SQL，再RAG</td></tr></table>

# 6.2 Hybrid Retrieval 管道

语义查询的完整流程如下（参考你在 Feishu bot 中规划的 Phase 1 方案）：

1. Query Rewriting：DeepSeek-V3 生成 2-3 个同义改写版本，同时做子问题分解

2. Dense Retrieval：BGE-M3 生成 query 向量，Qdrant similarity_search，top-20

3. Sparse Retrieval：BM25（jieba 分词），同一语料库，top-20

4. RRF Merge：Reciprocal Rank Fusion 融合两路结果，去重

5. Metadata Filter：按 ticker / date_range / collection 过滤

6. Cross-encoder Reranking：bge-reranker-v2-m3 精排，top-20 → top-5

7. Context Assembly $^ +$ LLM Generation：DeepSeek-V3 生成含来源标注的回答

from FlagEmbedding import BGEM3FlagModel   
from rank_bm25 import BM250kapi   
import jieba   
class HybridRetriever: def__init__(self): self.model $=$ BGEM3FlagModel('BAAI/bge-m3',use.fp16=True) self. reranker $=$ FlagReranker('BAAI/bge-reranker-v2-m3',use.fp16=True) def retrieve(self, query: str, collection: str, top_k=20, filters=None): # 1. Dense: BGE-M3 $\rightarrow$ Qdrant q_vec $=$ self.model.encode([query])[dense_vecs'][0] dense_hits $=$ qdrant.search(collection,q_vec,limit $\coloneqq$ top_k, query_filter $\equiv$ filters) #2.Sparse:BM25 (基于已入库文本的内存索引) bm25_hits $=$ self.vm25_search(query, collection, top_k)

3. Merge & Rerank (RRF)  
merged = rrf_merge(dense_hits, bm25_hits)  
4. Cross-encoder精排top-20 $\rightarrow$ top-5  
pairs $=$ [(query，hit/container["text"]）for hit in merged[:20]]  
scores $=$ self. reranker.compute_score(pairs)  
reranked $=$ sorted(zip(merged[:20]，scores)，key= lambda x:-x[1])  
return [hit for hit,_in reranked[:5]]

# 6.3 Reflection 层（Text2SQL）

直接复用 Feishu bot 的 Reflection 设计：Generate Evaluate Refine 三轮循环，最多 2 次Refine，超出则返回"无法确定"而非乱答。

# 7. 应用入口

# 7.1 Claude Skill（当前阶段入口）

在本地用 Claude Code 的 skill 机制作为最轻量的入口，快速验证检索质量，无需部署前端。Skill 调用本地运行的 FastAPI 服务（8001 端口） 。

```txt
---  
name: investment_rag  
description: >  
    查询A股投研知识库。支持：研报语义检索、公司公告问答、  
    量化因子查询(Text2SQL)、个人笔记检索。  
    触发关键词：研报、公告、因子、财务、分析、查一下、找一下  
---  
# Investment RAG Skill
```

工具调用 FastAPI 服务，合并语义检索与结构化查询结果。

## 使用示例

- "帮我查中矿资源最近的研报观点"

"贵州茅台 2024 年毛利率是多少"（→ Text2SQL）

- "找我的笔记里关于 Hormuz 的分析"（→ notes collection）

- "煤化工板块最近机构看法"（→ reports collection）

## API 调用

```json
POST http://localhost:8001/query  
{  
    "query": "<用户问题>",  
    "filters": {  
        "ticket": "<股票代码，可选>",  
        "date_from": "<YYYY-MM-DD，可选>",  
        "collection": "<reports|announcements|notes|macro，可选>"  
    },  
    "top_k": 5}
```

# 7.2 FastAPI 服务（Phase 4）

/query 接口的请求/响应设计：

```json
# POST /query   
Request: { "query": "中矿资源近期机构评级", "filters": { "ticket": "002738", # 可选 "date_from": "2024-01-01", # 可选 "collection": "reports" # 可选，不传则全库检索 }, "top_k": 5 } Response: { "answer": "根据检索到的3份研报...", "sources": [ {"file": "中矿资源_国泰君安_20240315.pdf", "page": 4, "score": 0.92}, ... ], "query_type": "semantic", # semantic | sql | hybrid "sql": null # Text2SQL场景下返回执行的SQL }
```

# 8. Prompt 模板设计

按查询类型配置独立 system prompt，避免通用 prompt 导致的角色混淆：

```txt
# prompts/research_qa.py
SYSTEM = ""
"你是一名专业的A股投资研究助手。
根据检索到的研报/公告内容，精准回答用户问题。
- 每个关键数据点必须标注来源（文件名+页码）
- 如果检索内容不足以回答，明确说明并建议补充数据来源
- 数字类回答保留原始精度，不要四舍五入
...
USER_template = ""
## 检索到的相关内容
{context}
## 用户问题
{question}
请基于以上内容回答，如有数字请引用原文。
```

# 9. 商业化设计（提前埋点）

这些不是 MVP 必须项，但架构上要留好扩展点，避免后期大改。

<table><tr><td>功能</td><td>实现方式</td><td>时间节点</td></tr><tr><td>用户认证</td><td>JWT / API Key, FastAPI middleware</td><td>Phase 4</td></tr><tr><td>用量计量</td><td>每次 /query 写 usage_log 表 (MySQL)</td><td>Phase 4</td></tr><tr><td>配额控制</td><td>Redis 计数器, 按 API Key 限速</td><td>Phase 4</td></tr><tr><td>知识库隔离</td><td>Qdrant Collection 按用户 namespace</td><td>商业化阶段</td></tr><tr><td>版权合规</td><td>研报只存摘要+结论, 公告存全文 (官方公开)</td><td>从 Phase 1 起执行</td></tr></table>

# 10. 黄金测试集设计

在入库 5-10 份文档后立即建立 20 条测试问答对，作为每次迭代的评估基准：

<table><tr><td>类型</td><td>示例问题</td><td>评估指标</td></tr><tr><td>财务数值</td><td>贵州茅台2024年营业收入是多少？</td><td>Exact Match,需附页码</td></tr><tr><td>分析类</td><td>机构对中芯国际的主要风险提示有哪些？</td><td>Rouge-L+人工评分</td></tr><tr><td>因子查询</td><td>当前PB最低的煤炭股TOP5？</td><td>SQL正确性+数值准确</td></tr><tr><td>跨库联合</td><td>营收增速&gt;20%的科技公司,找近3个月研报</td><td>两阶段均正确</td></tr><tr><td>笔记检索</td><td>我对Hormuz风险的分析结论是什么？</td><td>精确匹配笔记内容</td></tr></table>

# 11. 任务拆分 & 执行顺序

P0 = 阻塞性任务， 当天必须完成； $P \mathbf { 1 } =$ 核心功能， 本周内； $P 2 =$ $\underline { { \underline { { \mathbf { \delta \pi } } } } }$ 优化项， 可推迟。 估时为净编码时间，不含调试。

<table><tr><td>Phas e</td><td>任务</td><td>优 先 级</td><td>估 时</td><td>依赖</td><td>说明</td></tr><tr><td>P0</td><td>搭建基础设施: DockerCompose (Qdrant + Redis)</td><td>P0</td><td>2h</td><td>—</td><td>Qdrant 本地端口6333, Redis 做 metadata 缓</td></tr><tr><td></td><td></td><td></td><td></td><td></td><td>存</td></tr><tr><td>P0</td><td>初始化项目结构 + config.py + requirements.txt</td><td>P0</td><td>1h</td><td>—</td><td>参照目录结构,含MySQL复用myTrader连接</td></tr><tr><td>P0</td><td>BGE-M3 embedding 模型本地部署</td><td>P0</td><td>1h</td><td>P0-1</td><td>FlagEmbedding, use fp16=True, Mac本地推理</td></tr><tr><td>P0</td><td>Qdrant Client 封装 + Collection 初始化</td><td>P0</td><td>2h</td><td>P0-2</td><td>4个collection: reports/announcements/notes/macro</td></tr><tr><td>P1</td><td>PDF 解析模块 (MinerU/PyMuPDF)</td><td>P0</td><td>3h</td><td>P0完成</td><td>保留页码元数据,支持表格提取</td></tr><tr><td>P1</td><td>文本分块策略(RecursiveCharacterSplitter)</td><td>P0</td><td>2h</td><td>P1-1</td><td>chunk_size=800, overlap=150, 中文感知分块</td></tr><tr><td>P1</td><td>批量 Embedding + 写入 Qdrant 流水线</td><td>P0</td><td>3h</td><td>P1-2</td><td>含 metadata: ticker/date/source/report_type</td></tr><tr><td>P1</td><td>先跑通: 5份研报入库 + 基础 similarity_search 验证</td><td>P0</td><td>1h</td><td>P1-3</td><td>用你手头的煤化工/石化研报,快速冒烟测试</td></tr><tr><td>P2</td><td>BM25 稀疏检索实现</td><td>P1</td><td>2h</td><td>P1完成</td><td>rank_bm25, jieba 分词,与 BGE-M3 dense 融合</td></tr><tr><td>P2</td><td>Cross-encoderReranker (bge-eranker-v2-m3)</td><td>P1</td><td>2h</td><td>P2-1</td><td>精排 top-20 → 返回 top-5</td></tr><tr><td>P2</td><td>Query Rewriting 模块</td><td>P1</td><td>3h</td><td>P2-2</td><td>同义词扩展 + 子问题分解, DeepSeek-V3生成</td></tr><tr><td>P2</td><td>意图路由器 (结构化 vs 语义)</td><td>P1</td><td>3h</td><td>P2-1</td><td>复用 Feishu bot 路由架构,接 Text2SQL 分支</td></tr><tr><td>P3</td><td>cninfo 公告爬虫 (年报/季报/重大事项)</td><td>P1</td><td>4h</td><td>P1完成</td><td>优先A股正式公告,避免版权问题</td></tr><tr><td>P3</td><td>Obsidian 笔记同步入库</td><td>P1</td><td>2h</td><td>P1完成</td><td>vault 目录 watch, MD → 解析→ embed, 差异更新</td></tr><tr><td>P3</td><td>定时调度器(APScheduler)</td><td>P2</td><td>2h</td><td>P3-1,P3-2</td><td>每日增量爬取,触发重新embed</td></tr><tr><td>P4</td><td>FastAPI 服务封装 /query 接口</td><td>P1</td><td>3h</td><td>P2完成</td><td>请求体含 query/filters,响应含 sources+answer</td></tr><tr><td>P4</td><td>Claude Skill 文件编写</td><td>P1</td><td>2h</td><td>P4-1</td><td>参照本文附录,支持自然语言查询+结果格式化</td></tr><tr><td>P4</td><td>黄金测试集构建 + 自动评估</td><td>P2</td><td>3h</td><td>P4-1</td><td>20条问答对,评估Recall@5 / Answer 质量</td></tr></table>

# 12. 本地 + 云端分工

<table><tr><td>Mac 本地</td><td>开发调试、BGE-M3 推理（小批量）、Claude Skill 验证、Obsidian 笔记入库、Qdrant 本地实例</td></tr><tr><td>云端 ECS</td><td>Qdrant 生产实例（持久化）、FastAPI 服务、定时爬虫（公告/研报）、批量 Embedding Job</td></tr><tr><td>数据同步</td><td>本地开发完→同步云端，Qdrant 数据用 snapshot 备份；MySQL 已有 Tailscale 通道可直连</td></tr></table>

# 13. 快速启动（Docker Compose）

```yaml
version: '3.8'  
services:  
qdrant:  
    image: qdrant/qdrant:latest  
    ports:  
        - "6333:6333"  
    volumes:  
        - ./data/qdrant:/qdrant/storage  
redis:  
    image: redis:7-alpine  
    ports:  
        - "6379:6379"  
    volumes:  
        - ./data/redis:/data 
```

启动后验证：

```txt
curl http://localhost:6333collections # 应返回 {"result": {"collections": []}}
```

# 附录：建议的第一周行动清单

8. Day 1：docker-compose up，验证 Qdrant $^ +$ Redis 启动；BGE-M3 跑通 encode 测试

9. Day 2：PDF 解析 $^ +$ 分块 $^ +$ 写入 Qdrant，入库 5 份手头的煤化工/石化研报

10. Day 3：基础 similarity_search 验证，感受 NaïveRAG 天花板；建立 5 条黄金测试问题

11. Day 4：加 BM25 + Cross-encoder，对比检索质量提升

12. Day 5：FastAPI /query 接口 $^ +$ Claude Skill，端到端跑通第一个完整查询

最重要的是Day3的主观感受——亲眼看到NaiveRAG回答不了的问题，是后续所有优化的动力来源。不要跳过这一步。