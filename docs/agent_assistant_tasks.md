# 交易助手 Agent -- 任务拆分

> 基于 `docs/agent_assistant_design.md` 设计方案
> 日期: 2026-04-18

## 任务总览

共 **7 个阶段, 38 个任务**，按依赖顺序排列。

```
P0: 基础设施 (T01-T06)      -- 数据表、核心类、Prompt
P1: 内置工具 (T07-T13)       -- 8 个 Builtin Tools
P2: ReAct Loop (T14-T17)    -- 编排引擎、SSE 流式
P3: API 路由 (T18-T21)      -- 后端接口、权限
P4: 插件系统 (T22-T26)      -- Plugin 加载、投资大师
P5: 前端浮窗 (T27-T34)      -- 全局浮窗、对话 UI
P6: MCP 集成 (T35-T38)      -- MCP Client、外部工具
```

---

## P0: 基础设施

### T01: 创建 Agent 数据库表 + Alembic 迁移

**描述**: 新增 `agent_conversations` 和 `agent_messages` 两张表。

**具体内容**:
- 创建 Alembic 迁移脚本 `alembic/versions/xxx_add_agent_tables.py`
- `agent_conversations`: id(VARCHAR36 PK), user_id(INT), title(VARCHAR200), active_skill(VARCHAR100), created_at, updated_at
- `agent_messages`: id(BIGINT AUTO_INCREMENT PK), conversation_id(VARCHAR36), role(ENUM user/assistant/tool), content(TEXT), tool_calls(JSON), tool_call_id(VARCHAR100), tool_name(VARCHAR100), metadata(JSON), created_at
- 索引: conversation_id, user_id, updated_at, created_at
- ENGINE=InnoDB DEFAULT CHARSET=utf8

**单元测试**: `tests/unit/api/test_agent_models.py`
- 测试 ORM 模型字段定义正确
- 测试表关系 (conversation -> messages)
- 测试 JSON 字段序列化/反序列化

**验收标准**: `make migrate` 成功执行, 表结构正确

**依赖**: 无

---

### T02: 创建 Agent ORM 模型

**描述**: 在 `api/models/` 下创建 SQLAlchemy ORM 模型。

**具体内容**:
- `api/models/agent.py`: AgentConversation, AgentMessage 两个 ORM 类
- 遵循现有 ORM 模式 (参考 `api/models/user.py`)
- AgentConversation: relationship to messages (lazy="selectin")
- AgentMessage: ForeignKey to conversation_id

**单元测试**: 与 T01 合并

**依赖**: T01

---

### T03: 创建 AgentContext 和 ToolDef 数据结构

**描述**: 定义 Agent 系统的核心数据结构。

**具体内容**:
- `api/services/agent/__init__.py`: 包初始化
- `api/services/agent/schemas.py`:
  - `ToolDef` dataclass: name, description, parameters, source, handler, requires_tier, category
  - `AgentContext` dataclass: user, db, redis, conversation_id, page_context
  - `ToolCallResult` dataclass: name, result, call_id, duration_ms, success
  - `AgentMessage` (Pydantic): role, content, tool_calls, tool_call_id, tool_name

**单元测试**: `tests/unit/api/test_agent_schemas.py`
- 测试 ToolDef 构造和序列化
- 测试 AgentContext 构造
- 测试 ToolCallResult 字段默认值
- 测试 JSON Schema 参数校验

**依赖**: 无

---

### T04: 创建 ToolRegistry (工具注册中心)

**描述**: 统一管理三类工具来源 (builtin / plugin / mcp) 的注册与发现。

**具体内容**:
- `api/services/agent/tool_registry.py`:
  - `ToolRegistry` 类:
    - `register_builtin(tool_def: ToolDef)` -- 注册内置工具
    - `register_plugin(tool_def: ToolDef)` -- 注册插件工具
    - `register_mcp(tool_def: ToolDef)` -- 注册 MCP 工具
    - `get_tools_for_user(user: User) -> list[ToolDef]` -- 按 tier 过滤
    - `get_tool(name: str) -> ToolDef | None` -- 按名称查找
    - `get_openai_tools(user: User) -> list[dict]` -- 转换为 OpenAI tools format
    - `execute(name: str, params: dict, ctx: AgentContext) -> ToolCallResult` -- 执行工具
  - `builtin_tool` 装饰器: 注册函数为内置工具
  - 模块级 `_registry` 单例

**单元测试**: `tests/unit/api/test_agent_tool_registry.py`
- 测试注册 builtin tool 成功
- 测试注册重复 name 抛出异常
- 测试按 tier 过滤 (free 用户看不到 pro 工具)
- 测试 get_openai_tools 输出格式正确
- 测试 execute 调用正确的 handler
- 测试 execute 工具不存在时抛出异常
- 测试 ToolCallResult 包含 duration_ms

**依赖**: T03

---

### T05: 创建 ConversationStore (对话存储)

**描述**: 管理对话的创建、消息保存、历史加载、上下文压缩。

**具体内容**:
- `api/services/agent/conversation.py`:
  - `ConversationStore` 类:
    - `create(user_id: int, title: str = "") -> str` -- 创建对话, 返回 conv_id
    - `save_message(conv_id: str, role: str, content: str, **kwargs)` -- 保存消息
    - `get_messages(conv_id: str, limit: int = 20) -> list[dict]` -- 获取最近消息
    - `get_messages_for_llm(conv_id: str) -> list[dict]` -- 获取 LLM 格式消息 (含压缩)
    - `list_conversations(user_id: int, limit: int = 50) -> list[dict]` -- 对话列表
    - `delete_conversation(conv_id: str, user_id: int)` -- 删除对话
    - `update_title(conv_id: str, title: str)` -- 更新标题
  - Redis 缓存: 最近消息 LIST (TTL 2h)
  - 自动标题生成: 用对话首条消息的前 30 字符

**单元测试**: `tests/unit/api/test_agent_conversation.py`
- 测试创建对话返回 UUID
- 测试保存消息并读取
- 测试消息按时间排序
- 测试 get_messages limit 参数
- 测试 get_messages_for_llm 格式正确 (role/content)
- 测试 tool 消息包含 tool_call_id
- 测试删除对话同时删除消息
- 测试 list_conversations 只返回指定用户的
- 测试 Redis 缓存命中/未命中

**依赖**: T01, T02

---

### T06: 创建 System Prompt 模板

**描述**: 定义 Agent 的系统提示词。

**具体内容**:
- `api/services/agent/prompts.py`:
  - `AGENT_SYSTEM_PROMPT`: 基础人设 + 能力说明 + 行为约束
  - `build_system_prompt(page_context, active_skill, available_tools)`: 动态构建
  - 约束:
    - 禁止编造数据，数据不足时明确说明
    - action 类工具调用前需要解释原因
    - 回答使用中文
    - 不使用 emoji (MySQL utf8 兼容)

**单元测试**: `tests/unit/api/test_agent_prompts.py`
- 测试基础 prompt 包含关键指令
- 测试 page_context 注入 (market 页面 vs dashboard 页面)
- 测试 active_skill 的 system_prompt 被正确追加
- 测试 available_tools 列表被格式化到 prompt 中

**依赖**: 无

---

## P1: 内置工具 (Builtin Tools)

### T07: 实现 query_portfolio 工具

**描述**: 查询用户当前持仓列表。

**具体内容**:
- 在 `api/services/agent/builtin_tools.py` 中实现
- 复用 `api/services/portfolio_mgmt_service.py` 的查询逻辑
- 返回: stocks 列表 (code, name, quantity, cost_price, current_price, pnl_ratio)
- 无需参数 (从 ctx.user 获取 user_id)

**单元测试**: `tests/unit/api/test_agent_tools.py::TestQueryPortfolio`
- 测试有持仓时返回正确列表
- 测试无持仓时返回空列表
- 测试返回字段完整性

**依赖**: T04

---

### T08: 实现 get_stock_indicators 工具

**描述**: 获取指定股票技术指标。

**具体内容**:
- 复用 `signal_interpreter.py` 的 `_load_signals` 查询逻辑
- 参数: stock_code (required), days (optional, default=30)
- 返回: MA5/20/60/250, MACD (DIF/DEA/HIST), RSI, KDJ, volume_ratio, RPS_20
- 处理数据缺失: 返回 null 而非报错

**单元测试**: `tests/unit/api/test_agent_tools.py::TestGetStockIndicators`
- 测试正常股票返回指标
- 测试不存在的股票返回空结果
- 测试 stock_code 格式校验 (6位数字)

**依赖**: T04

---

### T09: 实现 search_knowledge 工具

**描述**: RAG 知识库检索。

**具体内容**:
- 复用 `investment_rag/retrieval/hybrid_retriever.py` + reranker
- 参数: query (required), collection (optional), top_k (optional, default=5)
- 返回: documents 列表 (source, text_snippet, score)
- 截断每个文档到 500 字符，防止 context 膨胀

**单元测试**: `tests/unit/api/test_agent_tools.py::TestSearchKnowledge`
- 测试检索返回结果格式正确
- 测试 top_k 参数生效
- 测试空查询返回空列表
- 测试文本截断逻辑

**依赖**: T04

---

### T10: 实现 query_database 工具

**描述**: 自然语言查结构化数据 (Text2SQL)。

**具体内容**:
- 复用 `investment_rag/retrieval/text2sql.py`
- 参数: query (required)
- 返回: sql (生成的 SQL), results (查询结果, 最多 50 条), columns
- 安全: 只允许 SELECT 语句，参数化查询

**单元测试**: `tests/unit/api/test_agent_tools.py::TestQueryDatabase`
- 测试正常查询返回结果
- 测试 SQL 注入防护 (DROP/DELETE/UPDATE 被拒绝)
- 测试结果条数限制 (max 50)

**依赖**: T04

---

### T11: 实现 get_fear_index 工具

**描述**: 获取市场恐慌指数。

**具体内容**:
- 复用 `data_analyst/sentiment/fear_index.py`
- 无参数
- 返回: vix, ovx, gvz, us10y, overall_level (low/medium/high/extreme), updated_at

**单元测试**: `tests/unit/api/test_agent_tools.py::TestGetFearIndex`
- 测试返回字段完整
- 测试 overall_level 值在预期范围内
- 测试服务不可用时的错误处理

**依赖**: T04

---

### T12: 实现 search_news 和 get_hot_sectors 工具

**描述**: 新闻搜索 + 热门板块。

**具体内容**:
- `search_news`:
  - 参数: query (required), stock_code (optional), days (optional, default=3)
  - 复用 `data_analyst/sentiment/news_fetcher.py`
  - 返回: news 列表 (title, source, date, summary), 最多 10 条
- `get_hot_sectors`:
  - 无参数
  - 复用申万行业轮动数据
  - 返回: sectors 列表 (name, change_pct, volume_ratio, rank)

**单元测试**: `tests/unit/api/test_agent_tools.py::TestSearchNews`, `TestGetHotSectors`
- search_news: 测试按关键词搜索、按 stock_code 搜索、空结果
- get_hot_sectors: 测试返回格式、排序正确

**依赖**: T04

---

### T13: 实现 add_watchlist 和 add_position action 工具

**描述**: 操作类工具 -- 添加关注 / 加入持仓。

**具体内容**:
- `add_watchlist`:
  - 参数: stock_code (required), stock_name (required), note (optional)
  - 调用 watchlist API 服务层
  - 返回: {success: true, message: "已添加到关注列表"}
- `add_position`:
  - 参数: stock_code (required), stock_name (required), quantity (optional)
  - 调用 portfolio_mgmt 服务层
  - requires_tier: "pro"
  - 返回: {success: true, message: "已添加到模拟持仓"}
- 这两个工具标记 category="action"，orchestrator 层面不做拦截，前端负责二次确认

**单元测试**: `tests/unit/api/test_agent_tools.py::TestActionTools`
- 测试添加关注成功
- 测试添加持仓成功
- 测试重复添加的处理
- 测试缺少必填参数报错

**依赖**: T04

---

## P2: ReAct Loop (编排引擎)

### T14: 实现 LLM Function Calling 客户端

**描述**: 扩展现有 LLMClientFactory，支持 tools + streaming 的 function calling 调用。

**具体内容**:
- `api/services/agent/llm_chat.py`:
  - `AgentLLMClient` 类:
    - `__init__(model_alias: str = "qwen")` -- 复用 LLMClientFactory 配置
    - `async def chat_stream(messages, tools) -> AsyncIterator[dict]` -- 流式 function calling
    - 处理 DashScope 流式 tool_calls 增量拼接
    - 返回事件: `{"type": "token", "content": "..."}` 或 `{"type": "tool_calls", "calls": [...]}`
  - 超时: 90 秒
  - 错误重试: 1 次

**单元测试**: `tests/unit/api/test_agent_llm_chat.py`
- Mock OpenAI client，测试流式文本输出解析
- Mock tool_calls 响应，测试增量拼接
- 测试超时处理
- 测试空响应处理

**依赖**: T03

---

### T15: 实现 AgentOrchestrator 核心 ReAct Loop

**描述**: 核心编排引擎，驱动 LLM -> Tool -> LLM 循环。

**具体内容**:
- `api/services/agent/orchestrator.py`:
  - `AgentOrchestrator` 类:
    - `__init__(tool_registry, llm_client, conversation_store)`
    - `async def chat(message, user, conversation_id, active_skill, page_context) -> AsyncIterator[dict]`
    - ReAct loop:
      1. 从 ConversationStore 加载历史消息
      2. 构建 system_prompt (含 page_context, active_skill)
      3. 获取用户可用的 tools
      4. 循环 (max 10 次迭代):
         - 调用 LLM (stream)
         - 如果有 tool_calls: 逐个执行, yield tool_call/tool_result 事件
         - 如果无 tool_calls: yield token 事件, break
      5. 保存所有消息到 ConversationStore
      6. yield done 事件
    - 错误处理: 任何异常 yield error 事件
    - 配额检查: 调用前检查 LLM 配额

**单元测试**: `tests/unit/api/test_agent_orchestrator.py`
- Mock LLM 返回纯文本 -> 测试直接回答
- Mock LLM 返回 tool_call -> 测试工具执行 -> 再次调用 LLM -> 回答
- Mock LLM 返回多个 tool_calls -> 测试顺序执行
- 测试 max_iterations 防止无限循环
- 测试工具执行失败时 yield error 到 LLM (继续推理)
- 测试消息保存到 ConversationStore
- 测试配额不足时直接返回 error 事件
- 测试 active_skill 的 system_prompt 注入

**依赖**: T04, T05, T06, T14

---

### T16: 实现 action 事件处理

**描述**: Agent 输出中识别操作指令，转换为 action 事件。

**具体内容**:
- 在 `orchestrator.py` 中:
  - 如果 LLM 调用了 category="action" 的工具 (如 add_watchlist):
    - yield `{"type": "action", "action": tool_name, "payload": params}` 事件
    - 前端收到后弹出确认对话框
    - 不立即执行，等待前端确认后调用对应 API
  - action 事件格式:
    - add_watchlist: `{"action": "add_watchlist", "payload": {"stock_code": "002594", "stock_name": "比亚迪"}}`
    - add_position: `{"action": "add_position", "payload": {"stock_code": "002594", "stock_name": "比亚迪"}}`
    - navigate: `{"action": "navigate", "payload": {"path": "/analysis?code=002594"}}`

**单元测试**: `tests/unit/api/test_agent_orchestrator.py::TestActionEvents`
- 测试 action tool 产生 action 事件而非直接执行
- 测试 action 事件格式正确
- 测试 navigate action 的 path 构建

**依赖**: T15, T13

---

### T17: Orchestrator 集成测试

**描述**: 端到端测试完整的 ReAct loop。

**具体内容**:
- `tests/integration/test_agent_orchestrator.py`:
  - 使用 Mock LLM (固定响应序列)
  - 使用内存 SQLite 数据库
  - 测试场景:
    1. 简单问答 (无 tool call)
    2. 单次 tool call (查持仓 -> 回答)
    3. 多次 tool call (查持仓 -> 查指标 -> 综合回答)
    4. action tool call (添加关注 -> action 事件)
    5. 工具执行失败 (优雅降级)
    6. 多轮对话 (上下文延续)
  - 验证 SSE 事件序列完整性

**依赖**: T15, T16, T07-T13

---

## P3: API 路由

### T18: 创建 Agent Pydantic Schemas

**描述**: 定义 API 请求/响应模型。

**具体内容**:
- `api/schemas/agent.py`:
  - `ChatRequest`: message(str, max 2000), conversation_id(str|None), active_skill(str|None), page_context(dict|None)
  - `ConversationSummary`: id, title, updated_at, message_count
  - `ConversationDetail`: id, title, messages[], created_at
  - `ToolInfo`: name, description, parameters, source, category, requires_tier
  - `MCPServerConfig`: name, transport, command|url, args, description

**单元测试**: `tests/unit/api/test_agent_schemas_api.py`
- 测试 ChatRequest message 长度限制
- 测试 ChatRequest 可选字段默认值
- 测试 ConversationSummary 序列化

**依赖**: 无

---

### T19: 实现 Agent API 路由 -- 对话接口

**描述**: POST /api/agent/chat SSE 流式端点。

**具体内容**:
- `api/routers/agent.py`:
  - `POST /api/agent/chat`: SSE 流式对话
    - 认证: `Depends(get_current_user)`
    - 输入: ChatRequest
    - 调用 AgentOrchestrator.chat()
    - 返回: StreamingResponse (text/event-stream)
    - Headers: Cache-Control, Connection, X-Accel-Buffering
  - 注册到 `api/main.py` 的 router 列表

**单元测试**: `tests/unit/api/test_agent_router.py::TestChatEndpoint`
- Mock orchestrator，测试 SSE 事件格式
- 测试未认证请求返回 401
- 测试消息超长返回 422

**依赖**: T15, T18

---

### T20: 实现 Agent API 路由 -- 对话管理接口

**描述**: 对话 CRUD 接口。

**具体内容**:
- `api/routers/agent.py` 中新增:
  - `GET /api/agent/conversations`: 对话列表 (分页)
  - `GET /api/agent/conversations/{id}`: 对话详情 (含消息)
  - `DELETE /api/agent/conversations/{id}`: 删除对话
  - `GET /api/agent/tools`: 可用工具列表
  - 所有接口需认证
  - conversations 只返回当前用户的

**单元测试**: `tests/unit/api/test_agent_router.py::TestConversationEndpoints`
- 测试列表返回用户的对话
- 测试详情包含消息列表
- 测试删除其他用户的对话返回 404
- 测试工具列表按 tier 过滤

**依赖**: T05, T18, T19

---

### T21: Agent API 集成测试

**描述**: 端到端 API 集成测试。

**具体内容**:
- `tests/integration/test_agent_api.py`:
  - 使用 httpx AsyncClient + 内存 SQLite
  - 测试场景:
    1. 发送消息获取 SSE 流 -> 解析事件 -> 验证完整性
    2. 创建对话 -> 发送多条消息 -> 获取对话详情 -> 消息完整
    3. 删除对话 -> 再次获取返回 404
    4. 获取工具列表 -> 验证 free/pro 工具过滤
    5. 未认证请求 -> 401
  - 遵循现有 `tests/integration/conftest.py` 模式

**依赖**: T19, T20

---

## P4: 插件系统

### T22: 实现 Plugin YAML 解析器

**描述**: 解析 `skill.yaml` 文件为 PluginSkillDef 对象。

**具体内容**:
- `api/services/agent/plugin_loader.py`:
  - `PluginSkillDef` dataclass: name, display_name, description, version, author, min_tier, type, system_prompt, required_tools, entry_point, parameters
  - `parse_skill_yaml(path: str) -> PluginSkillDef`: 解析单个 skill.yaml
  - 校验: 必填字段检查、type 枚举校验、entry_point 格式校验
  - 错误处理: 格式错误记录日志并跳过，不影响其他 plugin

**单元测试**: `tests/unit/api/test_agent_plugins.py::TestYAMLParser`
- 测试解析 prompt_skill YAML
- 测试解析 code_skill YAML
- 测试缺少必填字段抛出 ValueError
- 测试未知 type 值抛出 ValueError
- 测试空文件处理

**依赖**: T03

---

### T23: 实现 PluginLoader (插件加载器)

**描述**: 扫描 plugins/ 目录，加载所有插件为 ToolDef。

**具体内容**:
- `api/services/agent/plugin_loader.py` 中新增:
  - `PluginLoader` 类:
    - `__init__(plugins_dir: str)` -- 插件目录路径
    - `load_all() -> list[ToolDef]` -- 扫描并加载所有插件
    - `load_plugin(skill_def: PluginSkillDef) -> ToolDef` -- 加载单个插件
    - prompt_skill: 创建一个特殊 handler，返回 `{"type": "skill_activated", "system_prompt": ...}`
    - code_skill: 动态 import entry_point，包装为 handler
  - 启动时调用 `load_all()`, 注册到 ToolRegistry

**单元测试**: `tests/unit/api/test_agent_plugins.py::TestPluginLoader`
- 测试扫描 plugins/ 目录找到所有 skill.yaml
- 测试 prompt_skill 加载为 ToolDef
- 测试 code_skill 加载 + 动态 import
- 测试目录不存在时返回空列表
- 测试加载失败的 plugin 被跳过 (不影响其他)

**依赖**: T04, T22

---

### T24: 创建投资大师 Plugin -- 巴菲特 + 格雷厄姆

**描述**: 编写两个投资大师的 skill.yaml。

**具体内容**:
- `plugins/masters/buffett/skill.yaml`: 巴菲特价值投资框架 (参见设计文档 4.3)
- `plugins/masters/graham/skill.yaml`: 格雷厄姆安全边际框架
  - 核心要点: 低 PE (< 15)、低 PB (< 1.5)、股息率 > 2/3 AAA 债券利率
  - 流动资产 > 2x 流动负债、长期负债 < 净流动资产
  - 连续 20 年分红、10 年无亏损
- 两个 plugin 的 required_tools 都包含: query_database, search_knowledge, get_stock_indicators

**单元测试**: `tests/unit/api/test_agent_plugins.py::TestMasterPlugins`
- 测试 YAML 解析成功
- 测试 system_prompt 包含核心分析框架关键词
- 测试 required_tools 引用的工具在 ToolRegistry 中存在

**依赖**: T22

---

### T25: 创建更多投资大师 Plugin -- 彼得林奇 + 利弗莫尔 + 芒格

**描述**: 补充三个投资大师的 skill.yaml。

**具体内容**:
- `plugins/masters/peter_lynch/skill.yaml`:
  - PEG 分析、6 种股票分类 (慢速增长/稳定增长/快速增长/周期/困境反转/隐蔽资产)
  - "用常识投资"理念
- `plugins/masters/livermore/skill.yaml`:
  - 趋势跟踪、关键价位突破、金字塔加仓法
  - 市场时机判断 (以技术指标为主)
- `plugins/masters/munger/skill.yaml`:
  - 多学科思维模型、逆向思考
  - "好公司 + 好价格 + 长期持有"
  - 与巴菲特互补 (更侧重心智模型)
- 所有 plugin 配置 required_tools

**单元测试**: `tests/unit/api/test_agent_plugins.py::TestMoreMasterPlugins`
- 测试 3 个 YAML 解析成功
- 测试 system_prompt 非空且长度合理 (200-2000 字符)

**依赖**: T22

---

### T26: 实现 Orchestrator 与 Plugin 集成

**描述**: 让 AgentOrchestrator 支持 active_skill 参数。

**具体内容**:
- `orchestrator.py` 修改:
  - 当 `active_skill` 非空时:
    - 从 PluginLoader 获取对应 plugin
    - 将 plugin.system_prompt 追加到 system_prompt
    - 只暴露 plugin.required_tools + 通用工具
  - 当用户在对话中提到投资大师名字时 (如 "用巴菲特的视角")，LLM 可以通过调用 `activate_skill` 工具来激活
  - 新增 builtin tool: `activate_skill(skill_name: str)` -- 激活指定 plugin

**单元测试**: `tests/unit/api/test_agent_orchestrator.py::TestPluginIntegration`
- 测试 active_skill 注入 system_prompt
- 测试 required_tools 过滤生效
- 测试 activate_skill 工具调用后后续迭代使用新 prompt

**依赖**: T15, T23

---

## P5: 前端浮窗

### T27: 创建 Zustand Agent Store

**描述**: 前端全局状态管理。

**具体内容**:
- `web/src/lib/agent-store.ts`:
  - `useAgentStore`: isOpen, mode, conversationId, messages, isStreaming, activeSkill, pageContext
  - Actions: toggle, setMode, addMessage, clearMessages, setStreaming, setActiveSkill, updatePageContext, setConversationId
  - 消息类型: AgentMessage { id, role, content, toolCalls?, toolResult?, action?, timestamp }
  - 持久化: conversationId 存 localStorage

**单元测试**: 如项目有 vitest 则编写 store 测试
- 测试 toggle 切换 isOpen
- 测试 addMessage 追加消息
- 测试 clearMessages 清空

**依赖**: 无

---

### T28: 创建 useAgentChat Hook

**描述**: Agent 对话 SSE 通信 hook。

**具体内容**:
- `web/src/hooks/useAgentChat.ts`:
  - 基于现有 `useSSEFetch` 扩展
  - `useAgentChat()` 返回:
    - `sendMessage(content: string)`: 发送消息，启动 SSE 流
    - `isStreaming: boolean`
    - `cancel()`: 取消当前流
  - SSE 事件处理:
    - `thinking` -> 显示思考中状态
    - `tool_call` -> 追加工具调用卡片
    - `tool_result` -> 更新工具调用结果
    - `token` -> 追加到当前 assistant 消息
    - `action` -> 弹出确认对话框
    - `done` -> 结束流式
    - `error` -> 显示错误
  - 自动携带 JWT token
  - 超时: 5 分钟

**单元测试**: 无 (hook 逻辑在集成测试中覆盖)

**依赖**: T27

---

### T29: 创建 FloatingButton 组件

**描述**: 右下角常驻按钮。

**具体内容**:
- `web/src/components/agent/FloatingButton.tsx`:
  - 固定定位: right: 24px, bottom: 24px
  - 48px 圆形按钮，AI 图标 (SVG)
  - 点击切换 ChatPanel 展开/收起
  - hover 效果: 放大 + 阴影
  - z-index: 9990
  - 响应式: 移动端 right: 16px, bottom: 16px

**依赖**: T27

---

### T30: 创建 ChatPanel 面板

**描述**: 展开态对话面板。

**具体内容**:
- `web/src/components/agent/ChatPanel.tsx`:
  - 固定定位: right: 24px, bottom: 80px
  - 尺寸: 400px (width) x 600px (height)
  - 圆角 + 阴影 + border
  - 包含:
    - PanelHeader: 标题 ("交易助手") + 最小化按钮 + 全屏按钮 + 新对话按钮
    - MessageList: 消息列表容器 (flex: 1, overflow-y: auto, 自动滚动到底部)
    - QuickActions: 快捷操作按钮区
    - InputBar: 输入框 + 发送按钮
  - 全屏模式: 右侧 50% 宽度, 100% 高度
  - 展开/收起动画: CSS transform + transition (200ms)
  - z-index: 9999
  - 移动端: 全屏覆盖

**依赖**: T27, T29

---

### T31: 创建消息组件 (UserMessage + AssistantMessage + ToolCallCard)

**描述**: 对话中的各类消息展示。

**具体内容**:
- `web/src/components/agent/UserMessage.tsx`:
  - 用户消息气泡, 右对齐, 背景色区分
  - 显示时间戳

- `web/src/components/agent/AssistantMessage.tsx`:
  - AI 回答, 左对齐
  - 使用 react-markdown 渲染 Markdown 内容
  - 流式输出时显示闪烁光标
  - 思考中显示 "正在思考..." 动画

- `web/src/components/agent/ToolCallCard.tsx`:
  - 工具调用卡片, 默认折叠
  - 折叠态: "[工具] 查询了 002594 的技术指标" (一行摘要)
  - 展开态: 显示参数 + 返回结果 (JSON 格式化)
  - 加载中: 旋转图标
  - 成功/失败状态指示

**依赖**: T27

---

### T32: 创建 ActionConfirm 组件

**描述**: 操作类 action 的确认提示。

**具体内容**:
- `web/src/components/agent/ActionConfirm.tsx`:
  - 内联在消息流中的确认卡片
  - 显示: 操作描述 + [确认] [取消] 按钮
  - 确认后调用对应 API (watchlistApi.add / portfolioApi.add)
  - 取消后标记为已取消
  - 已执行/已取消后按钮置灰
  - navigate action: 确认后 router.push(path)

**依赖**: T27, T31

---

### T33: 创建 QuickActions 和 SkillSelector 组件

**描述**: 快捷操作和技能选择器。

**具体内容**:
- `web/src/components/agent/QuickActions.tsx`:
  - 根据 pageContext 动态显示快捷按钮
  - 点击快捷按钮 = 发送预设消息
  - 示例: [技术分析] -> "帮我分析一下 {stock_code} 的技术面"
  - 横向滚动, 不换行, 隐藏滚动条

- `web/src/components/agent/SkillSelector.tsx`:
  - 输入框左侧的技能选择按钮
  - 点击弹出技能列表 (从 GET /api/agent/tools 获取 plugin 类型的)
  - 选择后设置 activeSkill
  - 显示当前激活的技能标签

**依赖**: T27

---

### T34: 集成 FloatingAssistant 到 AppShell

**描述**: 将浮窗组件嵌入全局布局。

**具体内容**:
- `web/src/components/agent/FloatingAssistant.tsx`:
  - 组合 FloatingButton + ChatPanel
  - 根据 isOpen 切换显示
  - 监听 Ctrl+/ (Cmd+/) 快捷键
  - 监听 pathname 变化更新 pageContext

- 修改 `web/src/components/layout/AppShell.tsx`:
  - 在布局末尾添加 `<FloatingAssistant />`
  - 只在已认证页面渲染 (检查 user 状态)

- 修改 `web/src/lib/api-client.ts`:
  - 新增 `agentApi` 方法组:
    - `chat(req)` -- POST (通过 useAgentChat hook 直接 fetch, 不走 axios)
    - `listConversations()` -- GET
    - `getConversation(id)` -- GET
    - `deleteConversation(id)` -- DELETE
    - `listTools()` -- GET

**测试**: 手动验证
  - 所有页面右下角显示浮窗按钮
  - 点击展开对话面板
  - 发送消息收到 SSE 响应
  - 页面切换时快捷操作更新
  - 快捷键 Ctrl+/ 切换

**依赖**: T28-T33, T19, T20

---

## P6: MCP 集成

### T35: 实现 MCP Client 基础

**描述**: 连接 MCP Server，发现和调用 tools。

**具体内容**:
- `api/services/agent/mcp_client.py`:
  - `MCPToolSource` 类:
    - `async connect(config: MCPServerConfig)`: 连接 stdio/sse 类型 MCP Server
    - `async disconnect(name: str)`: 断开
    - `get_tools() -> list[ToolDef]`: 返回所有已连接 Server 的 tools
    - `async call_tool(server_name, tool_name, params) -> dict`: 调用
    - `_mcp_to_tooldef(mcp_tool) -> ToolDef`: 格式转换
  - 依赖: `pip install mcp` (`mcp` Python SDK)
  - 连接池: 保持长连接, 自动重连

**单元测试**: `tests/unit/api/test_agent_mcp.py`
- Mock MCP session, 测试 tool 发现
- Mock MCP session, 测试 tool 调用
- 测试格式转换 (MCP Tool -> ToolDef)
- 测试连接失败处理
- 测试断开连接

**依赖**: T04

---

### T36: 实现 MCP Server 管理 API

**描述**: 管理 MCP Server 配置的 admin 接口。

**具体内容**:
- `api/routers/agent.py` 中新增:
  - `POST /api/agent/mcp/servers`: 注册 MCP Server (admin only)
  - `GET /api/agent/mcp/servers`: 列出已注册的 MCP Server
  - `DELETE /api/agent/mcp/servers/{name}`: 删除 MCP Server
  - `POST /api/agent/mcp/servers/{name}/reconnect`: 重新连接
- MCP Server 配置存储在数据库 `agent_mcp_servers` 表 (或 .env 配置)

**单元测试**: `tests/unit/api/test_agent_router.py::TestMCPEndpoints`
- 测试 admin 用户可以注册 MCP Server
- 测试非 admin 用户返回 403
- 测试列出 servers
- 测试删除 server

**依赖**: T35, T19

---

### T37: MCP 与 ToolRegistry 集成

**描述**: MCP tools 自动注册到 ToolRegistry。

**具体内容**:
- 在 `api/services/agent/tool_registry.py` 中:
  - 添加 `load_mcp_tools(mcp_source: MCPToolSource)` 方法
  - 应用启动时自动加载配置的 MCP Server
  - MCP tool 的 source 标记为 "mcp"
  - MCP tool 名称加前缀避免冲突: `mcp_{server_name}_{tool_name}`

**单元测试**: `tests/unit/api/test_agent_tool_registry.py::TestMCPIntegration`
- 测试 MCP tools 注册到 registry
- 测试名称前缀正确
- 测试 MCP 连接失败不影响 builtin tools

**依赖**: T35, T04

---

### T38: 端到端 MCP 集成测试

**描述**: 完整的 MCP tool 发现 -> 注册 -> Agent 调用 测试。

**具体内容**:
- `tests/integration/test_agent_mcp_e2e.py`:
  - 启动一个 mock MCP Server (in-process)
  - 注册到 ToolRegistry
  - Agent 对话中触发 MCP tool 调用
  - 验证结果正确回传

**依赖**: T35, T36, T37

---

## 任务依赖图

```
P0 基础设施:
T01 ─→ T02 ─→ T05
T03 ─→ T04
T06

P1 内置工具:
T04 ─→ T07, T08, T09, T10, T11, T12, T13

P2 编排引擎:
T03 ─→ T14
T04 + T05 + T06 + T14 ─→ T15
T15 + T13 ─→ T16
T07-T16 ─→ T17

P3 API 路由:
T18
T15 + T18 ─→ T19
T05 + T18 + T19 ─→ T20
T19 + T20 ─→ T21

P4 插件系统:
T03 ─→ T22
T04 + T22 ─→ T23
T22 ─→ T24, T25
T15 + T23 ─→ T26

P5 前端:
T27
T27 ─→ T28, T29, T30, T31, T32, T33
T28-T33 + T19 + T20 ─→ T34

P6 MCP:
T04 ─→ T35
T35 + T19 ─→ T36
T35 + T04 ─→ T37
T35-T37 ─→ T38
```

## 建议执行顺序

| 优先级 | 阶段 | 任务 | 说明 |
|--------|------|------|------|
| 第一批 | P0 | T01-T06 | 基础设施, 并行开发 |
| 第二批 | P1 | T07-T13 | 内置工具, 可并行 |
| 第三批 | P2 | T14-T17 | 编排引擎, 串行 |
| 第四批 | P3 + P4 | T18-T26 | API + 插件, 可并行 |
| 第五批 | P5 | T27-T34 | 前端, 先 store/hook 再 UI |
| 第六批 | P6 | T35-T38 | MCP, 独立迭代 |

## 测试覆盖率要求

| 模块 | 最低覆盖率 | 测试方式 |
|------|-----------|---------|
| agent/orchestrator.py | 85% | unit + integration |
| agent/tool_registry.py | 90% | unit |
| agent/builtin_tools.py | 80% | unit |
| agent/plugin_loader.py | 85% | unit |
| agent/conversation.py | 80% | unit |
| agent/mcp_client.py | 75% | unit + integration |
| routers/agent.py | 80% | unit + integration |
| 总体 | >= 80% | pytest --cov |
