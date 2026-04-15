# LLM Agent 主题选股系统技术方案

**日期：** 2026-04-15
**版本：** v1.0

---

## 1. 整体架构：LLM Agent 框架

### 1.1 设计原则

LLM 对话创建主题只是"第一个技能"，整体设计为可扩展的 Skill 框架：

- 每个 Skill 是独立模块，实现统一基类接口
- 通过注册表路由，新增 Skill 无需修改框架代码
- 所有 Skill 走 SSE 流式返回，支持实时进度展示
- LLM 不负责代码准确性，代码验证由 DB 查询兜底

### 1.2 整体分层

```
[前端 Next.js]
      |  SSE 流式 / REST
[FastAPI 路由层]
  POST /api/theme-pool/llm/create     (P0，主题创建)
  POST /api/theme-pool/llm/stream     (M2，统一 Skill 路由)
      |
[LLM Agent 调度层]
  ThemeAgentDispatcher
    - 解析 skill_id
    - 调用对应 Skill.stream()
    - 管理 SSE 事件流
      |
[Skill 模块层]
  skill: theme-create        (P0，本方案实现)
  skill: theme-review        (M2，后续)
  skill: portfolio-doctor    (M3，后续)
      |
[数据源层]
  AKShareConceptFetcher      (东财概念板块，新增)
  LLMClient                  (investment_rag/embeddings/embed_model.py，现有)
  MySQL trade_stock_basic    (代码验证，现有)
  MySQL theme_pool / theme_pool_stocks (结果写入，现有)
```

### 1.3 技能注册机制

现有 `_ACTION_HANDLERS` dict 是同步/非流式模式。LLM Skill 独立维护一套注册表：

```
现有：_ACTION_HANDLERS dict  ->  同步函数，返回 dict
新增：_LLM_SKILL_REGISTRY dict  ->  Skill 实例，支持 .stream() 异步生成器
```

dispatcher 根据 `skill_id` 路由到对应 Skill，两套注册表并列，不互相干扰。

---

## 2. 数据源方案：AKShare 东财概念 + LLM 知识混合

### 2.1 两类数据源角色

**AKShare 东财概念板块（结构化事实层）**

- 接口：`ak.stock_board_concept_name_em()` 返回全量概念板块名称；`ak.stock_board_concept_cons_em(symbol=board_name)` 返回成分股
- 角色：提供权威的市场公认成分股，作为候选股票初始集合
- 局限：
  - 概念颗粒度粗，"电网设备"可能横跨多个板块（特高压、智能电网、电力设备等）
  - 板块名称与用户输入未必一一对应，需模糊匹配
  - 成分股质量参差，包含边缘受益个股，需 LLM 筛选
  - AKShare 同步 I/O，FastAPI 中需 `run_in_executor` 包装
  - 东财接口有频率限制，每次拉取需 0.3s 延迟

**LLM 知识（语义理解与补充层）**

- 使用：Qwen3-Max（现有 LLMClient）
- 角色：主题名映射到东财概念关键词；过滤弱相关个股；补充未覆盖的核心标的；生成每只股票关联理由
- 局限：
  - 训练数据有时效性，小市值冷门股认知薄弱
  - 可能生成不在 trade_stock_basic 中的无效代码，必须 DB 验证兜底
  - 调用延迟 3-10 秒，需流式返回改善体验

### 2.2 混合策略流程

```
用户输入主题名
       |
[LLM] 语义扩展：主题名 -> 相关东财概念关键词列表 (3-8个)
       |
[AKShare] 拉取概念列表 -> 模糊匹配命中板块 (2-5个)
       |
[AKShare] 逐板块拉取成分股 -> 合并去重 -> 原始候选池 (50-200只)
       |
[DB] 代码标准化 + 验证是否在 trade_stock_basic 中
       |
[LLM] 过滤+评分：输出精选列表 (20-40只) + 每只个股关联理由
       |
[LLM] 补充：5-10只 AKShare 未覆盖的主题核心标的
       |
[DB] 再次验证补充股票代码
       |
前端展示候选列表，用户勾选确认
```

---

## 3. P0 技能：主题创建（theme-create）

### 3.1 完整流程（按阶段）

**阶段 1：LLM 概念板块映射**

调用 LLM，传入主题名，输出相关东财概念板块关键词列表（JSON 格式，3-8个）。
发送事件：`{type: "concept_mapping", concepts: ["特高压", "智能电网", ...]}`

**阶段 2：AKShare 拉取成分股**

从全量板块列表中模糊匹配命中板块（关键词包含关系），逐板块拉取成分股并合并去重。
每个板块拉取时发送：`{type: "fetching", board: "特高压", status: "fetching|done", count: 45}`

**阶段 3：代码验证**

AKShare 返回 6 位代码（如 `000001`），标准化为 `000001.SZ`/`600519.SH` 格式，批量查询 `trade_stock_basic` 过滤无效代码。
发送：`{type: "raw_pool", total: 187, valid: 153, boards_hit: 4}`

**阶段 4：LLM 过滤精选**

将验证后的候选股（含代码、名称、所属板块）传给 LLM，输出过滤后精选列表（含 relevance 分级和一句话理由）。
发送：`{type: "filtering_start", total_candidates: 153}` -> `{type: "filter_done", selected: 32}`

**阶段 5：LLM 补充**

LLM 根据自身知识补充 5-10 只未在 AKShare 成分股中出现的核心标的，再次 DB 验证。
发送：`{type: "llm_supplement", stocks: [...]}`

**阶段 6：汇总与用户核验**

合并 AKShare 精选 + LLM 补充（按来源标记），发送最终 `candidate_list` 事件，SSE 结束。
前端展示候选列表，用户勾选/删除/手动补充，确认后调用现有 REST 端点写入 DB。

### 3.2 Prompt 设计

**CONCEPT_MAPPING_SYSTEM（阶段 1）**

```python
CONCEPT_MAPPING_SYSTEM = """你是 A 股东方财富概念板块专家。
给定一个主题名称，输出与该主题最相关的东方财富概念板块关键词列表。

约束：
1. 只输出 JSON 数组格式，不加任何解释
2. 关键词数量 3-8 个
3. 优先使用东方财富平台上实际存在的概念板块名称
4. 不要包含行业分类名（如"电力设备行业"），只用概念词（如"特高压"）

示例输出：
["特高压", "智能电网", "电力设备", "柔性直流", "电网改造"]"""
```

**STOCK_FILTER_SYSTEM（阶段 4）**

```python
STOCK_FILTER_SYSTEM = """你是 A 股主题投资专家，擅长识别主题驱动的受益标的。

任务：从候选股票列表中，筛选出与"{theme_name}"主题最相关的核心受益股。

输出格式（严格 JSON，不加任何额外文字）：
{{
  "selected": [
    {{
      "stock_code": "000001.SZ",
      "stock_name": "平安银行",
      "relevance": "high|medium",
      "reason": "一句话说明核心关联，限 50 字以内"
    }}
  ],
  "excluded_count": 32,
  "exclusion_summary": "简述主要排除原因"
}}

筛选标准：
- high: 核心业务直接属于该主题，主题直接受益方
- medium: 部分业务属于该主题，有间接受益逻辑
- 只输出 high 和 medium，low 直接排除"""
```

**LLM_SUPPLEMENT_SYSTEM（阶段 5）**

```python
LLM_SUPPLEMENT_SYSTEM = """你是 A 股投资专家。

任务：对于主题"{theme_name}"，补充 5-10 只重要的相关个股，这些股票未出现在已有候选列表中。

输出格式（严格 JSON）：
{{
  "supplements": [
    {{
      "stock_code": "600905.SH",
      "stock_name": "三峡能源",
      "reason": "一句话理由，限 50 字"
    }}
  ]
}}

重要约束：
1. stock_code 必须是真实存在的 A 股代码，格式为 XXXXXX.SH 或 XXXXXX.SZ
2. 不确定代码的个股宁可不写，不要猜测
3. 已在候选列表中的股票不要重复：{existing_codes_sample}"""
```

关键设计原则：
- 分三次 LLM 调用，每次职责单一，避免单次 prompt 过长
- 强制 JSON 输出，解析失败则重试一次，再失败降级处理
- LLM 不负责代码有效性，代码验证完全由 DB 查询完成

### 3.3 API 设计

**新增端点：POST /api/theme-pool/llm/create**

```python
class LLMThemeCreateRequest(BaseModel):
    theme_name: str
    description: str = ""
    max_candidates: int = 40

@router.post('/llm/create')
async def llm_create_theme(req: LLMThemeCreateRequest):
    """
    SSE streaming endpoint，事件类型按时序：
      {type: "start",           message: "..."}
      {type: "concept_mapping", concepts: [...]}
      {type: "fetching",        board: "...", status: "fetching|done", count: N}
      {type: "raw_pool",        total: N, valid: N, boards_hit: N}
      {type: "filtering_start", total_candidates: N}
      {type: "filter_done",     selected: N}
      {type: "llm_supplement",  stocks: [...]}
      {type: "candidate_list",  stocks: [...], total: N, akshare_count: N, llm_supplement_count: N}
      {type: "done",            summary: "..."}
      {type: "error",           message: "..."}

    candidate_list.stocks item schema:
      stock_code: "000001.SZ"
      stock_name: "平安银行"
      source: "akshare" | "llm"
      boards: ["特高压"]         // akshare 来源时填写
      relevance: "high" | "medium"
      reason: "..."
    """
    from api.services.theme_llm_service import ThemeCreateSkill

    async def event_gen():
        async for event in ThemeCreateSkill().stream(
            theme_name=req.theme_name,
            description=req.description,
            max_candidates=req.max_candidates,
        ):
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_gen(),
        media_type='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )
```

注意：`EventSource` 不支持 POST body，前端应使用 `fetch` + `ReadableStream` 手动解析 SSE 格式。

### 3.4 核心 Service 骨架

新增 `api/services/theme_llm_service.py`：

```python
class AKShareConceptFetcher:
    """东财概念板块数据拉取（同步 AKShare 包装为异步）"""

    async def get_all_boards(self) -> list[str]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_get_all_boards)

    def _sync_get_all_boards(self) -> list[str]:
        import akshare as ak
        df = ak.stock_board_concept_name_em()
        return df['板块名称'].tolist()

    async def get_board_stocks(self, board_name: str) -> list[dict]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_get_board_stocks, board_name)

    def _sync_get_board_stocks(self, board_name: str) -> list[dict]:
        import akshare as ak
        import time
        time.sleep(0.3)
        try:
            df = ak.stock_board_concept_cons_em(symbol=board_name)
            return [{'code': row['代码'], 'name': row['名称']} for _, row in df.iterrows()]
        except Exception as e:
            logger.warning('[AKShare] board %s failed: %s', board_name, e)
            return []


class StockCodeValidator:
    """代码标准化 + DB 验证"""

    def validate_batch(self, raw_codes: list[str]) -> dict[str, str]:
        normalized = [self._normalize(c) for c in raw_codes]
        placeholders = ','.join(['%s'] * len(normalized))
        rows = execute_query(
            f"SELECT stock_code, stock_name FROM trade_stock_basic "
            f"WHERE stock_code IN ({placeholders})",
            tuple(normalized), env='online',
        )
        return {r['stock_code']: r['stock_name'] for r in rows}

    @staticmethod
    def _normalize(code: str) -> str:
        code = code.strip().split('.')[0].zfill(6)
        if code.startswith(('0', '3')):   return f"{code}.SZ"
        elif code.startswith(('6', '9')): return f"{code}.SH"
        elif code.startswith(('4', '8')): return f"{code}.BJ"
        return f"{code}.SZ"


class ThemeCreateSkill:
    """P0 技能：LLM 对话创建主题，异步生成器模式"""

    async def stream(self, theme_name: str, description: str = "", max_candidates: int = 40):
        try:
            async for event in self._run(theme_name, description, max_candidates):
                yield event
        except Exception as e:
            logger.exception('[ThemeCreateSkill] unexpected error')
            yield {"type": "error", "message": str(e)}

    async def _run(self, theme_name, description, max_candidates):
        yield {"type": "start", "message": f"正在分析主题「{theme_name}」..."}
        # 阶段1: LLM 概念映射
        # 阶段2: AKShare 拉取
        # 阶段3: 代码验证
        # 阶段4: LLM 过滤
        # 阶段5: LLM 补充
        # 阶段6: 汇总
        # ... 完整实现见 api/services/theme_llm_service.py
```

### 3.5 前端交互设计

**入口**：在 `/theme-pool` 页面现有"创建主题"按钮旁增加"AI 创建"按钮，打开 `LLMCreateDialog` 组件。

**LLMCreateDialog 状态机**：

```
idle -> concept_mapping -> fetching -> filtering -> review -> creating -> done
                                                         \-> error
```

**候选列表 UI 要点**：
- 默认全选，用户可逐一取消勾选
- 按来源分组：AKShare 成分股在上（标记所属板块），LLM 补充在下（标记"AI 推荐"）
- 每只股票显示：代码、名称、来源标记、关联理由（可展开）
- 支持手动输入 6 位代码添加（调用 `GET /api/theme-pool/validate-code` 验证后加入）
- 确认按钮显示"将写入 N 只股票"，点击后复用现有 REST 端点写入

**SSE 读取方案**（fetch + ReadableStream，支持 POST body）：

```typescript
// web/src/hooks/useSSEFetch.ts
export function useSSEFetch() {
  const stream = async (url: string, body: object, onEvent: (e: any) => void) => {
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const reader = resp.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n\n');
      buffer = lines.pop() ?? '';
      for (const chunk of lines) {
        if (chunk.startsWith('data: ')) {
          try { onEvent(JSON.parse(chunk.slice(6))); } catch {}
        }
      }
    }
  };
  return { stream };
}
```

---

## 4. 技能扩展接口：Skill 基类规范

### 4.1 LLMSkillBase 抽象基类

新增 `api/services/llm_skills/base.py`：

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator, Any


@dataclass
class SkillMeta:
    skill_id: str       # 唯一标识，如 "theme-create"
    name: str           # 显示名，如 "主题创建"
    version: str        # 语义版本，如 "1.0.0"
    description: str    # 功能描述
    requires_llm: bool = True
    min_tier: str = "free"


class LLMSkillBase(ABC):
    """所有 LLM Skill 的基类。

    事件约定：
    - 每个事件必须有 "type" 字段
    - 最后一个成功事件 type 必须是 "done"
    - 错误事件 type 为 "error"，含 "message" 字段
    - 中间进度事件命名：{阶段}_{start|progress|done}
    """

    @property
    @abstractmethod
    def meta(self) -> SkillMeta: ...

    @abstractmethod
    async def stream(self, **kwargs: Any) -> AsyncIterator[dict]:
        """执行技能，流式返回 SSE 事件 dict。
        
        约定：
        1. 内部捕获所有异常，转为 {type: "error", message: "..."} 事件
        2. 最终 yield {type: "done", ...}
        3. DB 写入操作由调用层（router）在 stream 结束后执行，Skill 内不写 DB
        """
        ...

    async def validate_params(self, **kwargs: Any) -> None:
        """可选：参数校验，抛 ValueError 表示参数无效。"""
        pass
```

### 4.2 注册表

```python
# api/services/llm_skills/registry.py
_REGISTRY: dict[str, type] = {}

def register(skill_cls):
    meta = skill_cls().meta
    _REGISTRY[meta.skill_id] = skill_cls
    return skill_cls

def get_skill(skill_id: str) -> LLMSkillBase | None:
    cls = _REGISTRY.get(skill_id)
    return cls() if cls else None

def list_skills() -> list[dict]:
    return [
        {'skill_id': cls().meta.skill_id, 'name': cls().meta.name,
         'version': cls().meta.version, 'description': cls().meta.description}
        for cls in _REGISTRY.values()
    ]
```

### 4.3 后续技能扩展规范

新增技能只需：
1. 创建 `api/services/llm_skills/your_skill.py`
2. 继承 `LLMSkillBase`，实现 `meta` 和 `stream()`
3. 加 `@register` 装饰器

**M2：主题复评（theme-review）**

```python
@register
class ThemeReviewSkill(LLMSkillBase):
    # skill_id: "theme-review"
    # stream 参数: theme_id: int
    # 功能: 读取主题成分股最新得分，LLM 评估每只股票当前逻辑是否仍成立
    # 输出: 每只股票复评结论（维持/关注/建议移出）+ 理由
```

**M3：持仓健诊（portfolio-doctor）**

```python
@register
class PortfolioDoctorSkill(LLMSkillBase):
    # skill_id: "portfolio-doctor"
    # stream 参数: portfolio_id: int
    # 功能: 分析持仓集中度、行业风险敞口、主题重叠度，给出调仓建议
```

**M3：信号解读（signal-interpreter）**

```python
@register
class SignalInterpreterSkill(LLMSkillBase):
    # skill_id: "signal-interpreter"
    # stream 参数: stock_code: str
    # 功能: 将技术面信号 + 候选池评分转为自然语言投研摘要
```

---

## 5. 任务拆分

### M1：P0 功能上线（预计 2 周）

**目标**：LLM 对话创建主题完整跑通，数据流端到端可用。

| 任务 | 产出文件 | 依赖 |
|------|----------|------|
| M1-T1: AKShareConceptFetcher | `api/services/theme_llm_service.py` | 无 |
| M1-T2: StockCodeValidator | 同上，含代码标准化单测 | trade_stock_basic |
| M1-T3: Prompt 模板 | `api/services/theme_llm_prompts.py` | 无 |
| M1-T4: ThemeCreateSkill.stream() | 完整异步生成器，全部阶段事件 | T1,T2,T3 |
| M1-T5: SSE 路由端点 | `api/routers/theme_pool.py` 新增端点 | T4 |
| M1-T6: LLM Skill 基类 | `api/services/llm_skills/base.py` + `registry.py` | 无 |
| M1-T7: useSSEFetch hook | `web/src/hooks/useSSEFetch.ts` | 无 |
| M1-T8: LLMCreateDialog 组件 | `web/src/components/theme-pool/LLMCreateDialog.tsx` | T5,T7 |
| M1-T9: 主题池页面集成 | `web/src/app/theme-pool/page.tsx` 增加入口 | T8 |
| M1-T10: 集成测试 | 端到端冒烟 | T1~T9 |

**M1 验收标准**：
- 输入"电网设备"，30 秒内看到候选列表（至少 15 只）
- 所有候选股在 trade_stock_basic 中可验证通过
- 用户确认后 theme_pool_stocks 中正确写入
- AKShare 超时、LLM 格式错误时能降级，不崩溃

### M2：框架完善 + 第二个 Skill（预计 3 周）

| 任务 | 产出 |
|------|------|
| M2-T1: 多模型切换 | `api/services/llm_client_factory.py`，env var 控制 Qwen/DeepSeek/Doubao |
| M2-T2: LLM 调用重试 | JSON 解析失败自动重试 1 次，全局 30s timeout |
| M2-T3: AKShare 结果缓存 | Redis 缓存概念板块数据，TTL 6 小时 |
| M2-T4: theme-review Skill | 主题复评功能完整实现 |
| M2-T5: 复评前端 | `/theme-pool/[themeId]` 页面添加复评按钮和结果展示 |
| M2-T6: 统一 Skill 路由 | `POST /api/theme-pool/llm/stream`，通过 `skill_id` 路由 |
| M2-T7: 用量日志 | LLM 调用耗时、token 用量写入 usage_logs 表 |

### M3：扩展技能集（预计 4 周）

| 任务 | 产出 |
|------|------|
| M3-T1: portfolio-doctor | 持仓健诊 Skill |
| M3-T2: signal-interpreter | 技术信号解读 Skill |
| M3-T3: 用户反馈机制 | 对 LLM 输出标记"有帮助/无帮助"，数据回流 |
| M3-T4: 配额精细化 | 按 skill_id 独立计算 token 用量 |
| M3-T5: 多模型 A/B | 同一请求双模型对比，前端展示 |

---

## 6. 模型选型建议

### 6.1 各模型对 A 股的适用性

**Qwen3-Max（当前已接入，推荐默认）**

- 优势：对主流 A 股主题（特高压、新能源、半导体等）认知准确；OpenAI 兼容 API，零改造成本；JSON 格式遵从性稳定
- 局限：北交所/科创板冷门股认知有限；小市值补充阶段幻觉率较高
- 用途：全阶段默认模型；概念映射阶段可换 `qwen3-8b` 降成本

**DeepSeek-V3**

- 优势：复杂推理任务表现突出（持仓风险分析、策略解读）；cost 较低，适合大候选池过滤；OpenAI 兼容接口，切换简单
- 局限：股票代码准确率略低于 Qwen；历史上 API 稳定性有波动，需配置 fallback
- 用途：M2 引入，用于过滤阶段和持仓健诊场景

**Doubao（字节豆包）**

- 优势：中文指令跟随和 JSON 输出格式稳定性好；超长上下文（128K+），一次传入更多候选
- 局限：对细分主题（专精特新、北交所）认知深度不如前两者
- 用途：M2 作为备选，A/B 测试评估

### 6.2 多模型切换实现

```python
# api/services/llm_client_factory.py
_MODEL_CONFIGS = {
    "qwen":       {"model": "qwen3-max",          "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "api_key_env": "RAG_API_KEY"},
    "qwen-fast":  {"model": "qwen3-8b",            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "api_key_env": "RAG_API_KEY"},
    "deepseek":   {"model": "deepseek-chat",       "base_url": "https://api.deepseek.com/v1",                      "api_key_env": "DEEPSEEK_API_KEY"},
    "doubao":     {"model": "doubao-pro-128k",     "base_url": "https://ark.cn-beijing.volces.com/api/v3",         "api_key_env": "DOUBAO_API_KEY"},
}

def get_llm_client(model_alias: str = None) -> LLMClient:
    alias = model_alias or os.getenv("LLM_MODEL_ALIAS", "qwen")
    cfg = _MODEL_CONFIGS.get(alias, _MODEL_CONFIGS["qwen"])
    # 构造 LLMClient，复用现有接口
    ...
```

通过 `LLM_MODEL_ALIAS` 环境变量切换，业务代码无需改动。

### 6.3 各阶段推荐模型

| 阶段 | 任务 | 推荐模型 | 原因 |
|------|------|----------|------|
| 阶段 1：概念映射 | 关键词扩展，短输出 | qwen-fast | 任务简单，节省成本和延迟 |
| 阶段 4：过滤精选 | 100+ 只候选股分析 | qwen3-max 或 deepseek | 需要较强的业务理解 |
| 阶段 5：LLM 补充 | 代码生成（高幻觉风险） | qwen3-max | A 股代码准确率相对更高 |
| M3 持仓健诊 | 复杂推理 | deepseek-v3 | 推理任务 DeepSeek 更有优势 |

---

## 7. 文件清单

### 新增文件

| 路径 | 说明 |
|------|------|
| `api/services/theme_llm_service.py` | ThemeCreateSkill、AKShareConceptFetcher、StockCodeValidator |
| `api/services/theme_llm_prompts.py` | 三个 prompt 模板常量 |
| `api/services/llm_client_factory.py` | 多模型切换工厂 |
| `api/services/llm_skills/__init__.py` | 包初始化 |
| `api/services/llm_skills/base.py` | LLMSkillBase 抽象基类、SkillMeta |
| `api/services/llm_skills/registry.py` | 技能注册表 + @register 装饰器 |
| `api/services/llm_skills/theme_create.py` | ThemeCreateSkill（基类版本，M2 重构时迁移） |
| `web/src/hooks/useSSEFetch.ts` | SSE fetch hook |
| `web/src/components/theme-pool/LLMCreateDialog.tsx` | AI 创建主题对话框 |

### 修改文件

| 路径 | 改动 |
|------|------|
| `api/routers/theme_pool.py` | 新增 POST /api/theme-pool/llm/create 端点 |
| `web/src/app/theme-pool/page.tsx` | 添加"AI 创建"按钮，引入 LLMCreateDialog |

### 现有文件直接复用

| 路径 | 用途 |
|------|------|
| `investment_rag/embeddings/embed_model.py` | LLMClient |
| `api/services/theme_pool_service.py` | create_theme + batch_add_stocks |
| `data_analyst/fetchers/akshare_fetcher.py` | AKShare 使用参考 |
