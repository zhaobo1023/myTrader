# 交易助手 Agent 系统设计方案

> 版本: v1.0 | 日期: 2026-04-18

## 1. 概述

### 1.1 目标

在 myTrader Web 平台中引入一个 **对话式交易助手**，以常驻浮窗形式嵌入所有页面右下角。用户可通过自然语言与 Agent 交互，Agent 自主决定调用哪些工具、按什么顺序执行，最终给出综合分析和建议。

### 1.2 核心能力

| 能力 | 说明 |
|------|------|
| 多轮对话 | 支持上下文连续追问，记忆对话历史 |
| 自主工具调用 | LLM (Qwen) 通过 function calling 自主选择和调用工具 |
| 内置工具 (Builtin Tools) | 包装现有服务：持仓查询、技术指标、RAG 检索、SQL 查询、恐慌指数等 |
| 插件技能 (Plugin Skills) | YAML 定义的投资大师分析框架，支持社区贡献 |
| MCP 集成 | 连接 MCP Server 生态，引入实时行情、新闻检索等外部工具 |
| 页面联动 | 在对话中触发前端操作：添加关注、加入持仓、跳转分析页等 |
| 流式输出 | SSE 实时展示推理过程、工具调用、文本生成 |

### 1.3 设计原则

1. **零外部 Agent 框架依赖** -- 基于 DashScope Qwen function calling 自建 ReAct loop
2. **复用现有基础设施** -- Skill Gateway、LLM Skills、SSE streaming、JWT 权限体系
3. **统一工具接口** -- Builtin / Plugin / MCP 三类工具共用 ToolDef 协议
4. **渐进式扩展** -- 先跑通核心 loop + 内置工具，再逐步接入 plugin 和 MCP

### 1.4 与现有系统的关系

```
现有 Skill Gateway (/api/skill/*)       -> 保留，处理单次调用场景
现有 LLM Skills (stream-based)          -> 保留，复杂流式场景继续使用
新增 Agent (/api/agent/*)               -> 多轮对话 + 自主工具调用
```

Agent 不替代现有系统，而是在更高层编排它们。Agent 的 builtin tools 内部会复用现有服务代码。

---

## 2. 系统架构

### 2.1 整体架构

```
+---------------------------------------------------------------+
|  前端 - 常驻浮窗 (所有页面右下角)                                 |
|  FloatingAssistant                                             |
|  +-----------------------------------------------------------+|
|  | ChatPanel (展开态)                                          ||
|  | +-------------------------------------------------------+ ||
|  | | MessageList                                            | ||
|  | |   UserMessage / AssistantMessage / ToolCallMessage     | ||
|  | +-------------------------------------------------------+ ||
|  | | QuickActions (页面感知的快捷操作)                         | ||
|  | | [技术分析] [加入关注] [持仓诊断] [巴菲特视角]             | ||
|  | +-------------------------------------------------------+ ||
|  | | InputBar + SkillSelector                               | ||
|  | +-------------------------------------------------------+ ||
|  +-----------------------------------------------------------+|
+---------------------------------------------------------------+
         | POST /api/agent/chat (SSE)
         v
+---------------------------------------------------------------+
|  后端 - api/routers/agent.py                                    |
|  +-----------------------------------------------------------+|
|  | POST /chat            多轮对话主入口                        ||
|  | GET  /conversations    对话列表                             ||
|  | GET  /conversations/:id  对话详情                           ||
|  | DELETE /conversations/:id  删除对话                         ||
|  | GET  /tools            可用工具列表                         ||
|  | POST /tools/mcp        注册 MCP Server (admin)             ||
|  +-----------------------------------------------------------+|
+---------------------------------------------------------------+
         |
         v
+---------------------------------------------------------------+
|  核心引擎 - api/services/agent/                                  |
|                                                                 |
|  +------------------+    +------------------+                   |
|  | AgentOrchestrator|    | ConversationStore|                   |
|  | (ReAct Loop)     |--->| (Redis + MySQL)  |                   |
|  +------------------+    +------------------+                   |
|         |                                                       |
|         v                                                       |
|  +------------------+                                           |
|  | ToolRegistry     |                                           |
|  | (统一工具注册)    |                                           |
|  +--------+---------+                                           |
|           |                                                     |
|    +------+--------+--------+                                   |
|    v               v        v                                   |
|  Builtin        Plugin    MCP                                   |
|  Tools          Skills    Client                                |
|  (8-10个)       (YAML)   (动态发现)                              |
+---------------------------------------------------------------+
```

### 2.2 工具来源与统一接口

```python
@dataclass
class ToolDef:
    """所有工具的统一定义"""
    name: str               # 工具唯一标识, 如 "query_portfolio"
    description: str        # LLM 用此决定是否调用
    parameters: dict        # JSON Schema (OpenAI tools format)
    source: str             # "builtin" | "plugin" | "mcp"
    handler: Callable       # async (params: dict, ctx: AgentContext) -> dict
    requires_tier: str      # "free" | "pro"
    category: str           # "data" | "analysis" | "action" | "external"
```

### 2.3 AgentContext

```python
@dataclass
class AgentContext:
    """工具执行时的上下文"""
    user: User              # 当前用户
    db: AsyncSession        # 数据库会话
    redis: aioredis.Redis   # Redis 客户端
    conversation_id: str    # 对话 ID
    page_context: dict      # 前端页面上下文 (当前页面、选中的股票等)
```

### 2.4 ReAct Loop 流程

```
用户消息
   |
   v
构建 messages (system_prompt + history + user_msg)
   |
   v
获取可用 tools (根据用户 tier 过滤)
   |
   v
+---> DashScope Qwen chat (messages + tools)
|        |
|        v
|     有 tool_calls?
|        |
|     +--+--+
|     |     |
|    YES    NO
|     |     |
|     v     v
|   执行   流式输出最终回答
|   工具      |
|     |       v
|   yield   yield tokens
|   events     |
|     |       done
|     v
+--- 追加结果到 messages, 继续 loop
     (max 10 次迭代)
```

### 2.5 SSE 事件协议

```
事件类型         | 数据结构                                         | 说明
----------------|--------------------------------------------------|------------------
thinking        | {type, iteration}                                | Agent 开始推理
tool_call       | {type, name, params, call_id}                    | 决定调用某工具
tool_result     | {type, name, result, call_id, duration_ms}       | 工具返回结果
token           | {type, content}                                  | 流式文本输出
action          | {type, action, payload}                          | 前端操作指令
done            | {type, conversation_id, usage}                   | 完成
error           | {type, message, code}                            | 错误
```

### 2.6 前端操作指令 (action 事件)

Agent 可以通过 action 事件触发前端操作：

```json
{"type": "action", "action": "add_watchlist", "payload": {"stock_code": "002594", "stock_name": "比亚迪"}}
{"type": "action", "action": "navigate", "payload": {"path": "/analysis?code=002594"}}
{"type": "action", "action": "add_position", "payload": {"stock_code": "002594"}}
{"type": "action", "action": "show_chart", "payload": {"stock_code": "002594", "period": "daily"}}
```

前端收到 action 事件后，弹出确认提示，用户确认后执行对应操作。

---

## 3. 内置工具 (Builtin Tools)

### 3.1 工具清单

| 工具名 | 分类 | 描述 | 数据来源 | Tier |
|--------|------|------|----------|------|
| `query_portfolio` | data | 查询用户当前持仓 | portfolio_mgmt_stocks 表 | free |
| `get_stock_indicators` | data | 获取股票技术指标 (MA/MACD/RSI/KDJ/量比/RPS) | trade_stock_indicators 表 | free |
| `search_knowledge` | data | RAG 知识库检索 (研报/公告/笔记) | ChromaDB + BM25 | free |
| `query_database` | data | 自然语言查结构化数据 (财报/交易/因子) | Text2SQL -> MySQL | free |
| `get_fear_index` | data | 获取市场恐慌指数 (VIX/OVX/GVZ/US10Y) | fear_index service | free |
| `search_news` | data | 搜索新闻舆情 | news_fetcher / AKShare | free |
| `run_tech_scan` | analysis | 技术面扫描 (信号检测) | tech_scan service | pro |
| `get_hot_sectors` | data | 获取热门板块轮动数据 | sw_rotation 表 | free |
| `add_watchlist` | action | 添加股票到关注列表 | watchlist API | free |
| `add_position` | action | 添加股票到模拟持仓 | portfolio_mgmt API | pro |

### 3.2 实现模式

每个 builtin tool 是一个 async 函数，通过装饰器注册：

```python
from api.services.agent.tool_registry import builtin_tool

@builtin_tool(
    name="query_portfolio",
    description="查询用户当前持仓列表，返回股票代码、名称、持仓数量、成本价、当前市值、盈亏比例。"
                "当用户询问'我的持仓'、'我买了什么'、'持仓风险'等问题时使用。",
    parameters={
        "type": "object",
        "properties": {},
        "required": []
    },
    category="data",
    requires_tier="free",
)
async def query_portfolio(params: dict, ctx: AgentContext) -> dict:
    # 复用现有 portfolio_mgmt_service 逻辑
    ...
```

---

## 4. 插件技能 (Plugin Skills)

### 4.1 Plugin 类型

| 类型 | 定义方式 | 适用场景 |
|------|---------|---------|
| prompt_skill | YAML (system_prompt) | 投资大师、分析框架 -- 不需要写代码 |
| code_skill | YAML + Python handler | 自定义选股、计算逻辑 -- 需要代码 |

### 4.2 目录结构

```
plugins/
├── masters/                        # 投资大师系列 (prompt_skill)
│   ├── buffett/
│   │   └── skill.yaml
│   ├── graham/
│   │   └── skill.yaml
│   ├── peter_lynch/
│   │   └── skill.yaml
│   ├── livermore/
│   │   └── skill.yaml
│   └── munger/
│       └── skill.yaml
├── community/                      # 社区贡献 (code_skill)
│   └── _example/
│       ├── skill.yaml
│       └── handler.py
└── __init__.py
```

### 4.3 skill.yaml 格式

```yaml
# prompt_skill 示例: 巴菲特价值投资分析
name: buffett_analysis
display_name: "巴菲特价值投资分析"
description: >
  用沃伦-巴菲特的投资框架分析股票。当用户说"用巴菲特的眼光看"、
  "价值投资分析"、"护城河分析"时触发。
version: "1.0.0"
author: "myTrader"
min_tier: "free"
type: "prompt_skill"

system_prompt: |
  你是一位资深的价值投资分析师，严格遵循沃伦-巴菲特的投资哲学。
  分析任何股票时，必须按照以下框架逐项评估：

  ## 1. 护城河 (Economic Moat)
  - 品牌价值、专利壁垒、网络效应、成本优势、转换成本
  - 护城河是在加宽还是在收窄？

  ## 2. 财务质量 (Financial Quality)
  - ROE 是否连续 5 年 > 15%
  - 自由现金流是否持续为正
  - 负债率是否合理 (资产负债率 < 60%)
  - 毛利率趋势

  ## 3. 管理层评估 (Management)
  - 管理层是否诚信、透明
  - 资本配置能力 (分红 vs 再投资 vs 回购)
  - 是否有大量内部人持股

  ## 4. 估值判断 (Valuation)
  - 当前 PE/PB 与历史分位数
  - DCF 内在价值估算
  - 安全边际是否充足 (巴菲特要求 > 25%)

  ## 5. 最终结论
  - 是否符合"用合理价格买入优秀公司"的标准
  - 明确给出：买入 / 持有 / 观望 / 回避

  要求：
  - 始终用数据说话，引用具体财务指标数值
  - 如果数据不足，明确指出哪些数据缺失
  - 不要模棱两可，给出明确判断

# 这个 skill 需要 agent 调用哪些内置工具
required_tools:
  - query_database
  - search_knowledge
  - get_stock_indicators
```

```yaml
# code_skill 示例: RPS 动量选股
name: rps_momentum_scan
display_name: "RPS 动量选股"
description: >
  基于 RPS 相对强度排名的动量选股策略。
  当用户说"RPS 选股"、"动量排名"、"强势股筛选"时触发。
version: "1.0.0"
author: "community"
min_tier: "pro"
type: "code_skill"

entry_point: "plugins.community.rps_momentum.handler"

parameters:
  type: object
  properties:
    top_n:
      type: integer
      default: 20
      description: "选取 RPS 排名前 N 的股票"
    min_rps:
      type: number
      default: 90
      description: "最低 RPS 阈值"
  required: []
```

### 4.4 Plugin 加载机制

1. 启动时扫描 `plugins/` 目录下所有 `skill.yaml`
2. 解析为 `PluginSkillDef` 对象
3. prompt_skill: 创建一个特殊的 tool，调用时将 system_prompt 注入到 Agent 上下文
4. code_skill: 动态 import entry_point，包装为标准 ToolDef

---

## 5. MCP 集成

### 5.1 配置

在 `.env` 或数据库 `agent_mcp_servers` 表中配置：

```json
{
  "mcp_servers": [
    {
      "name": "finance-news",
      "transport": "stdio",
      "command": "npx",
      "args": ["@example/finance-news-mcp"],
      "description": "金融新闻和公告检索",
      "enabled": true
    },
    {
      "name": "market-data",
      "transport": "sse",
      "url": "http://localhost:3001/mcp",
      "description": "实时行情数据",
      "enabled": true
    }
  ]
}
```

### 5.2 实现

```python
class MCPToolSource:
    """管理多个 MCP Server 连接，动态发现和调用 tools"""

    async def connect(self, server_config: dict) -> None:
        """连接一个 MCP Server"""

    async def disconnect(self, server_name: str) -> None:
        """断开连接"""

    def get_tools(self) -> list[ToolDef]:
        """返回所有已连接 MCP Server 的 tools (转换为统一 ToolDef)"""

    async def call_tool(self, server_name: str, tool_name: str, params: dict) -> dict:
        """调用指定 MCP Server 的 tool"""
```

### 5.3 依赖

使用 `mcp` Python SDK (`pip install mcp`)，不引入 NanoBot 或其他 agent 框架。

---

## 6. 对话管理

### 6.1 数据模型

新增数据库表 `agent_conversations` 和 `agent_messages`：

```sql
CREATE TABLE agent_conversations (
    id VARCHAR(36) PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(200) DEFAULT '',
    active_skill VARCHAR(100) DEFAULT NULL COMMENT '当前激活的 plugin skill',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_user_id (user_id),
    INDEX idx_updated_at (updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;

CREATE TABLE agent_messages (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    conversation_id VARCHAR(36) NOT NULL,
    role ENUM('user', 'assistant', 'tool') NOT NULL,
    content TEXT,
    tool_calls JSON DEFAULT NULL COMMENT 'assistant 的 tool_call 请求',
    tool_call_id VARCHAR(100) DEFAULT NULL COMMENT 'tool 消息对应的 call_id',
    tool_name VARCHAR(100) DEFAULT NULL,
    metadata JSON DEFAULT NULL COMMENT '额外数据: token 用量等',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_conversation_id (conversation_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
```

### 6.2 上下文管理策略

- **短期**: 最近 20 轮消息直接放入 LLM context
- **中期**: 超过 20 轮时，用 LLM 对早期消息做摘要压缩
- **持久**: 全部消息存 MySQL，支持历史回看

### 6.3 Redis 缓存

- `agent:conv:{conv_id}:messages` -- 最近消息列表 (LIST, TTL 2h)
- `agent:conv:{conv_id}:summary` -- 压缩摘要 (STRING, TTL 24h)

---

## 7. 前端设计

### 7.1 常驻浮窗架构

```
FloatingAssistant (全局组件, 嵌入 AppShell)
├── FloatingButton            # 右下角圆形按钮 (收起态)
│   ├── 未读消息计数
│   └── 点击展开 ChatPanel
├── ChatPanel                 # 展开态面板 (400x600px)
│   ├── PanelHeader           # 标题 + 最小化/全屏/关闭
│   ├── MessageList           # 消息列表 (虚拟滚动)
│   │   ├── UserMessage       # 用户消息气泡
│   │   ├── AssistantMessage  # AI 回答 (Markdown 渲染)
│   │   ├── ToolCallCard      # 工具调用卡片 (可折叠)
│   │   └── ActionConfirm     # 操作确认提示
│   ├── QuickActions          # 页面感知快捷操作按钮
│   └── InputBar              # 输入框 + 发送按钮 + 技能选择器
└── SkillDrawer               # 技能选择抽屉 (可选)
```

### 7.2 页面感知 (Page Context)

浮窗组件通过 `usePathname()` 和页面状态感知当前上下文，动态调整快捷操作：

| 页面 | 快捷操作 | 自动注入的 page_context |
|------|---------|------------------------|
| /market | [技术分析] [加入关注] [AI 解读] | {page: "market", stock_code: 选中的股票} |
| /dashboard | [持仓诊断] [风控检查] [调仓建议] | {page: "dashboard"} |
| /analysis | [深度分析] [对比分析] [巴菲特视角] | {page: "analysis", stock_code} |
| /strategy | [策略评估] [参数优化建议] | {page: "strategy", strategy_id} |
| /sentiment | [热点解读] [关联持仓分析] | {page: "sentiment"} |
| /theme-pool | [主题评估] [成分股扫描] | {page: "theme-pool", theme_id} |
| 其他页面 | [通用问答] [持仓概览] | {page: pathname} |

### 7.3 交互模式

- **收起态**: 右下角 48px 圆形按钮，显示 AI 图标
- **展开态**: 400x600px 浮窗面板，可拖拽调整位置
- **全屏态**: 占据右侧 50% 宽度，类似侧边栏
- **快捷键**: `Ctrl+/` 或 `Cmd+/` 切换展开/收起
- **动画**: 展开/收起使用 CSS transform + transition

### 7.4 前端状态管理

在 Zustand store 中新增 `useAgentStore`：

```typescript
interface AgentState {
    isOpen: boolean;
    mode: 'floating' | 'fullscreen';
    conversationId: string | null;
    messages: AgentMessage[];
    isStreaming: boolean;
    activeSkill: string | null;
    pageContext: Record<string, unknown>;

    toggle: () => void;
    setMode: (mode: 'floating' | 'fullscreen') => void;
    sendMessage: (content: string) => void;
    setActiveSkill: (skillId: string | null) => void;
    updatePageContext: (ctx: Record<string, unknown>) => void;
    clearConversation: () => void;
}
```

---

## 8. DashScope Function Calling 集成

### 8.1 调用方式

使用 OpenAI 兼容格式调用 DashScope：

```python
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("RAG_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

response = client.chat.completions.create(
    model="qwen-max",
    messages=messages,
    tools=[
        {
            "type": "function",
            "function": {
                "name": "query_portfolio",
                "description": "查询用户当前持仓...",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        },
        # ... more tools
    ],
    stream=True,   # 流式输出
)
```

### 8.2 流式 Tool Calling 处理

DashScope 的 streaming + function calling 返回格式与 OpenAI 一致：

```python
async def _stream_chat(self, messages, tools):
    """流式调用 LLM，处理 tool_calls 和文本输出"""
    response = client.chat.completions.create(
        model=self.model,
        messages=messages,
        tools=tools,
        stream=True,
    )

    tool_calls_buffer = {}
    for chunk in response:
        delta = chunk.choices[0].delta

        # 文本内容
        if delta.content:
            yield {"type": "token", "content": delta.content}

        # tool call 增量
        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index
                if idx not in tool_calls_buffer:
                    tool_calls_buffer[idx] = {
                        "id": tc.id, "name": tc.function.name, "arguments": ""
                    }
                if tc.function.arguments:
                    tool_calls_buffer[idx]["arguments"] += tc.function.arguments

    # 返回完整的 tool_calls
    if tool_calls_buffer:
        yield {
            "type": "tool_calls",
            "calls": list(tool_calls_buffer.values())
        }
```

---

## 9. 安全与权限

### 9.1 认证

- 复用现有 JWT 认证 (`get_current_user` 依赖)
- 浮窗组件共享页面的 access_token

### 9.2 工具权限

- 每个 ToolDef 声明 `requires_tier`
- ToolRegistry 根据用户 tier 过滤可用工具
- action 类工具 (add_watchlist, add_position) 需要前端二次确认

### 9.3 配额控制

- 复用现有 `LLMQuotaService`
- 每次 Agent 对话消耗 1 次 LLM 配额 (不论内部迭代几次)
- Admin 用户不受配额限制

### 9.4 输入安全

- 用户消息长度限制 (max 2000 字符)
- tool_call 参数校验 (JSON Schema validation)
- SQL 注入防护 (Text2SQL 使用参数化查询)
- system_prompt 注入防护 (plugin system_prompt 不拼接用户输入)

---

## 10. 文件结构

```
api/services/agent/                    # Agent 核心引擎
├── __init__.py
├── orchestrator.py                    # ReAct loop 核心
├── tool_registry.py                   # 统一工具注册与发现
├── builtin_tools.py                   # 内置工具定义
├── plugin_loader.py                   # Plugin YAML 加载器
├── mcp_client.py                      # MCP Server 连接管理
├── conversation.py                    # 对话上下文管理
└── prompts.py                         # System prompt 模板

api/routers/agent.py                   # Agent API 路由
api/schemas/agent.py                   # Pydantic 请求/响应模型

plugins/                               # 插件目录
├── __init__.py
├── masters/                           # 投资大师 (prompt_skill)
│   ├── buffett/skill.yaml
│   ├── graham/skill.yaml
│   ├── peter_lynch/skill.yaml
│   ├── livermore/skill.yaml
│   └── munger/skill.yaml
└── community/                         # 社区贡献 (code_skill)
    └── _example/
        ├── skill.yaml
        └── handler.py

alembic/versions/                      # 数据库迁移
└── xxx_add_agent_tables.py

web/src/components/agent/             # 前端组件
├── FloatingAssistant.tsx              # 浮窗入口 (全局)
├── FloatingButton.tsx                 # 圆形按钮
├── ChatPanel.tsx                      # 展开态面板
├── PanelHeader.tsx                    # 面板头部
├── MessageList.tsx                    # 消息列表
├── UserMessage.tsx                    # 用户消息
├── AssistantMessage.tsx               # AI 回答 (Markdown)
├── ToolCallCard.tsx                   # 工具调用卡片
├── ActionConfirm.tsx                  # 操作确认
├── QuickActions.tsx                   # 快捷操作
├── InputBar.tsx                       # 输入框
└── SkillSelector.tsx                  # 技能选择器

web/src/hooks/useAgentChat.ts          # Agent 对话 hook (SSE)
web/src/lib/agent-store.ts            # Zustand Agent 状态

tests/unit/api/test_agent_orchestrator.py
tests/unit/api/test_agent_tools.py
tests/unit/api/test_agent_router.py
tests/unit/api/test_agent_plugins.py
tests/unit/api/test_agent_conversation.py
tests/unit/api/test_agent_mcp.py
tests/integration/test_agent_e2e.py
tests/unit/web/                        # 前端组件测试 (如有 vitest)
```

---

## 11. 技术规范 (后续开发必须遵循)

### 11.1 新增 Builtin Tool 规范

1. 在 `api/services/agent/builtin_tools.py` 中使用 `@builtin_tool` 装饰器
2. 必须提供 `description` -- 这是 LLM 决定是否调用的唯一依据
3. `parameters` 使用标准 JSON Schema
4. handler 签名统一为 `async def func(params: dict, ctx: AgentContext) -> dict`
5. 返回值必须是可 JSON 序列化的 dict
6. 异常不要吞掉，抛出让 orchestrator 统一处理
7. 数据查询类工具返回结果不超过 50 条记录，防止 context 膨胀

### 11.2 新增 Plugin Skill 规范

1. 在 `plugins/` 对应子目录下创建文件夹，包含 `skill.yaml`
2. prompt_skill: 只需要 `system_prompt` + `required_tools`，不需要代码
3. code_skill: 需要 `entry_point` 指向一个 async handler 函数
4. `description` 字段必须包含触发关键词（LLM 据此匹配）
5. 不要在 plugin 中直接访问数据库，通过 `required_tools` 声明依赖

### 11.3 SSE 事件规范

1. 每个事件必须有 `type` 字段
2. 最后一个成功事件必须是 `type: "done"`
3. 错误事件 `type: "error"` + `message` + `code`
4. 工具调用事件必须包含 `call_id` 用于前端匹配
5. action 事件必须包含 `action` + `payload`，前端需二次确认

### 11.4 前端组件规范

1. Agent 相关组件统一放在 `web/src/components/agent/`
2. 使用 `useAgentStore` 管理全局状态，不要在组件内用 useState 管理对话数据
3. SSE 通信使用 `useAgentChat` hook（基于现有 `useSSEFetch` 扩展）
4. 所有操作类 action 必须有确认步骤，不允许静默执行
5. 工具调用展示默认折叠，点击展开详情
6. 遵循现有的 inline style 模式（项目未使用 CSS modules）

### 11.5 测试规范

1. 每个 builtin tool 至少 3 个单元测试：正常输入、边界输入、异常输入
2. orchestrator 测试需 mock LLM 响应和工具执行
3. plugin loader 测试需覆盖 YAML 解析、格式校验、加载失败
4. 集成测试覆盖完整对话流程 (发消息 -> tool call -> 回答)
5. 单元测试覆盖率要求 >= 80%
6. 使用 pytest + pytest_asyncio，遵循现有 conftest.py 模式
