# LangGraph 交易团队工作流调研报告

> 原案例路径：`/Users/zhaobo/data0/person/quant/CASE-交易团队工作流（langgraph）`
> 调研日期：2026-04-22

---

## 一、整体架构

4 个 AI Agent + 1 个人在回路节点，通过 LangGraph StateGraph 编排：

```
Charles(投研) -> Zoe(信号) -> Kris(风控) -> [重试循环] -> Human(interrupt) -> Trader(下单)
```

**相对传统 Agent 模式的核心优势**：
- 硬卡点：用 `interrupt()` 在图里真正暂停，不依赖 prompt 约束
- 可调度：可挂在 cron/APScheduler 自动触发，无需用户交互
- 可恢复：用 MemorySaver checkpointer 持久化，支持崩溃恢复

---

## 二、完整目录结构

```
CASE-交易团队工作流（langgraph）/
├── main.py                          # 入口：手动运行一次完整工作流
├── graph.py                         # 核心：StateGraph 工作流定义（节点+边+路由逻辑）
├── state.py                         # 状态契约：TradingState 所有字段定义
├── scheduler.py                     # 定时调度：APScheduler 自动触发工作流
├── requirements.txt
│
├── nodes/
│   ├── charles_node.py              # 投研情报官：DeepAgents Agent，产出 investment_view
│   ├── zoe_node.py                  # 信号官：MACD 回测 + 多因子决策矩阵，产出 trade_signal
│   ├── kris_node.py                 # 风控官：8 条规则风控引擎，产出 risk_verdict
│   ├── human_node.py                # 人在回路：interrupt 机制暂停，等待人类授权
│   └── trader_node.py               # 交易执行：miniQMT 下单（支持 dry-run）
│
├── lib/
│   ├── risk_engine.py               # Kris 的风控逻辑（8 条规则）
│   └── miniqmt_trader.py            # Trader 的 QMT 接口
│
├── scripts/
│   ├── run_backtest.py              # MACD 回测脚本（供 Zoe 调用）
│   ├── get_kline.py                 # 获取 K 线数据（供 Kris ATR 计算）
│   └── sync_charles_vendor.py
│
├── vendor/charles_agent/            # Charles 节点的完整依赖
│   ├── agent.py                     # DeepAgents Agent 定义（6 个 @tool）
│   ├── data/vector_store/           # 本地 RAG 知识库（860 chunks）
│   └── skills/                      # 8 个可插拔 Skill
│
└── outputs/
    ├── reports/                     # 每次运行的研报（Markdown + HTML）
    └── runs/                        # 每次运行的完整 state（JSON）
```

---

## 三、核心状态契约

`TradingState` 是系统的状态中枢，采用 "State as a Contract" 设计：

```python
class TradingState(TypedDict):
    # 输入
    stock_code: str
    capital: float
    user_question: str

    # 各节点产出
    investment_view: InvestmentView    # Charles 的投研观点
    trade_signal: TradeSignal          # Zoe 的交易信号
    risk_verdict: RiskVerdict          # Kris 的风控决议
    approved: Optional[bool]           # Human 的授权标志
    trade_result: TradeResult          # Trader 的下单回执

    # 控制流
    retry_count: int                   # Kris 否决后回到 Zoe 的重试次数
    max_retry: int

    # 审计日志（Annotated[list, add] 支持多节点 append）
    messages: Annotated[list, add]
```

关键细节：`messages` 用 `Annotated[list, add]` 让多节点可以追加日志，最后自动合并为完整对话历史。

---

## 四、工作流拓扑

```
START
  |
charles  [投研] 产出 investment_view
  |
zoe      [信号] 产出 trade_signal
  |
kris     [风控] 产出 risk_verdict
  |
  +-- (kris reject && retry < max) --> zoe_retry [递增 retry_count] --> zoe [重试]
  +-- (kris reject && retry == max) --> END [终止]
  +-- (kris approve) --> human [人在回路 interrupt]
                              |
                         (approved?)
                          +-- no  --> END
                          +-- yes --> trader [下单] --> END
```

**条件边路由代码**：

```python
def route_after_kris(state: dict) -> str:
    verdict = state.get("risk_verdict", {})
    retry = int(state.get("retry_count", 0))
    max_retry = int(state.get("max_retry", 2))
    decision = verdict.get("decision", "approve")

    if decision in ("halt", "reject"):
        if retry >= max_retry:
            return END  # 连续否决达上限，终止
        return "zoe_retry"  # 回到 Zoe 缩量重发
    return "human"

# 中转节点（负责递增计数，路由函数不能改 state）
def zoe_retry_bump(state: dict) -> dict:
    return {"retry_count": int(state.get("retry_count", 0)) + 1}

g.add_conditional_edges("kris", route_after_kris,
    {"zoe_retry": "zoe_retry", "human": "human", END: END})
g.add_edge("zoe_retry", "zoe")
```

---

## 五、四大 Agent 角色详解

### 5.1 Charles 投研情报官

**职责**：深度研究分析，输出投资观点

**6 个工具**：
- `web_search` - 联网搜索最新市场信息
- `query_pdf` - 本地 RAG 知识库查询（860 chunks）
- `stock_price` - K 线数据获取
- `financial_analysis` - 财务指标分析
- `compare_reports_period` - 纵向时期对比
- `compare_reports_company` - 横向公司对比

**输出结构**：
```python
investment_view = {
    "stance": "bullish",              # bullish/neutral/bearish
    "confidence": 0.85,               # 0-1
    "summary": "一句话核心观点",
    "catalysts": ["催化剂1", "催化剂2"],
    "risks": ["风险1", "风险2"],
    "raw_report": "完整 Markdown 研报",
    "report_md_path": "/path/to/.md",
    "report_html_path": "/path/to/.html"
}
```

**创新设计**：
- 强制结构化输出：prompt 末尾附加 `EXTRACT_SUFFIX` 要求 JSON 摘要，确保下游能解析
- JSON 容错解析：`_find_json_blocks()` 扫描所有平衡 `{...}` 块，反向尝试（摘要通常在末尾）
- 报告双份输出：同时生成 Markdown（纯正文）和 HTML（带样式）

---

### 5.2 Zoe 信号官

**职责**：技术面交易信号生成，MACD 回测 + 多因子共振矩阵

**决策矩阵**：

| 技术面（MACD）| 基本面（Charles）| 决策 |
|---|---|---|
| golden_cross | bullish | buy（标准仓位）|
| death_cross | bearish | sell |
| bullish | bullish | buy（高信心）|
| bearish | bearish | sell |
| golden_cross/bullish | neutral | buy（小仓试探）|
| 强势 bullish(0.7+) | 技术分歧 | buy（0.5x 仓位试探）|
| 其他 | | hold |

**仓位计算**：
```python
pos_pct = _decide_position_pct(stance, confidence) * suggested_max_pct
# suggested_max_pct 来自 Kris 上一轮的降级建议

if direction == "buy":
    amount = capital * pos_pct
    quantity = int(amount / latest_close / 100) * 100  # 100 股整数倍
```

**关键**：当 Kris 给出 `suggested_max_pct < 1.0` 时，Zoe 自动缩量重发，体现闭环反馈。

---

### 5.3 Kris 风控官

**职责**：交易前风险评估，输出 approve/warn/reject/halt

**8 条风控规则**：

| 分类 | 规则 | 实现逻辑 |
|------|------|------|
| 事前 | 单笔金额上限 | 防 bug/fat-finger |
| 事前 | 价格偏离（Price Collar）| 委托价与现价偏离 > 5% 警告 |
| 事前 | ST 黑名单 | 拦截退市风险股 |
| 事前 | ATR 仓位（海龟法则）| 让每笔交易承担恒定 1% 风险 |
| 事中 | 单日最大亏损熔断 | 日损失 > 2% 停止交易 |
| 事中 | ATR 止损 | 基于 ATR(14) 动态止损 |
| 外部 | 事件关键词 | 黑名单词汇触发 reject |
| 外部 | 宏观 VIX 门控 | VIX > 25 时降仓 |

**ATR 海龟仓位法则（核心）**：
```python
atr = _fetch_kline_atr(stock)       # ATR(14)，来自最近 60 根日 K
risk_per_share = atr * atr_risk_pct
max_shares = capital * 0.01 / risk_per_share  # 最多能买多少股

if qty > max_shares * atr_overshoot_ratio:
    decision = Decision.WARN
    suggested_max_pct = max_shares / qty  # 建议缩量，不直接否决
```

**输出结构**：
```python
risk_verdict = {
    "decision": "approve",       # approve/warn/reject/halt
    "is_approved": True,         # warn 也算通过
    "reason": "所有检查通过",
    "suggested_max_pct": 1.0     # < 1.0 时 Zoe 应缩量
}
```

---

### 5.4 Human 人在回路

**机制**：LangGraph `interrupt()` 硬卡点

```python
def human_review_node(state: dict) -> dict:
    payload = {
        "stock": ..., "direction": ..., "quantity": ...,
        "charles_stance": ..., "zoe_reason": ..., "kris_decision": ...
    }
    user_decision = interrupt(payload)  # 硬卡在这里
    approved = user_decision.strip().lower() in ("y", "yes", "ok", "approve", "1", "true")
    return {"approved": approved}
```

**调用方式**：
```python
# 第一段：跑到 interrupt
state = graph.invoke(initial_state, config=config)

# 检测是否卡在 human_review
snapshot = graph.get_state(config)
if "human" in snapshot.next:
    payload = snapshot.tasks[0].interrupts[0].value
    # 展示审批信息...
    user_reply = input("是否授权下单 (yes/no): ")
    
    # 第二段：恢复执行
    state = graph.invoke(Command(resume=user_reply), config=config)
```

---

### 5.5 Trader 交易执行

```python
if os.environ.get("TRADER_DRY_RUN", "1") == "1":
    # Dry-run：仅打印，不下单
    return {"dry_run": True, "note": f"dry-run: buy {qty} @ {price}"}
else:
    # 真下单：调用 miniQMT
    trader = MiniQMTTrader(qmt_path, account_id)
    trader.connect()
    order_id = trader.buy(stock, qty, price, strategy_name="team-workflow")
    trader.disconnect()
    return {"dry_run": False, "order_id": order_id}
```

---

## 六、重试闭环详解

**典型场景**：
1. Zoe 建议买 1000 股
2. Kris 计算 ATR 超标，给 `suggested_max_pct = 0.5`，`decision = warn`（通过，但建议缩量）
3. 若 `decision = reject`：触发 `zoe_retry`，递增 `retry_count`，Zoe 读取 `suggested_max_pct = 0.5` 后缩量至 500 股重发
4. Kris 重新评估 500 股，通常通过
5. Human 审批，Trader 下单

---

## 七、定时调度

```python
# scheduler.py
scheduler = BlockingScheduler()
scheduler.add_job(
    run_workflow_job,
    trigger=CronTrigger(day_of_week="mon-fri", hour=9, minute=25),
    args=[stock_code, capital, question, auto_approve]
)
scheduler.start()
```

同一个 `run_workflow()` 函数，既支持手动运行（`main.py`），也支持 cron 自动触发。

---

## 八、值得 myTrader 借鉴的设计

### P0 优先级

| 设计 | 说明 | 对应 myTrader 模块 |
|------|------|--------------------|
| ATR 海龟仓位法则 | `max_shares = capital * 1% / ATR(14)`，每笔恒定 1% 风险 | `risk_manager/` |
| `suggested_max_pct` 建议缩量 | 风控不是一票否决，而是建议仓位，策略层自动缩量重发 | `risk_manager/` + `executor/` |
| `interrupt()` 大单审批硬卡点 | 真正暂停图执行，基于 checkpointer 持久化，崩溃可恢复 | `api/routers/` + Agent |

### P1 优先级

| 设计 | 说明 | 对应 myTrader 模块 |
|------|------|--------------------|
| 基本面 x 技术面共振矩阵 | 9 种 case 的明确仓位倍率，比纯技术扫描更完整 | `strategist/tech_scan/` |
| 风控闭环重试（kris->zoe->kris）| 条件边 + 中转节点，最多 max_retry 次 | Agent 工作流 |
| 事件关键词黑名单 | 从研报风险点提取文本做关键词检查 | `risk_manager/` |
| VIX 宏观门控 | VIX > 25 时自动降仓比例 | `risk_manager/` |

### P2 优先级

| 设计 | 说明 | 对应 myTrader 模块 |
|------|------|--------------------|
| 完整 state 落盘（run JSON）| 每次执行序列化完整状态，用于事后复盘 | `output/runs/` |
| `Annotated[list, add]` 决策日志 | 每个节点追加时间戳日志，自动合并为完整决策链 | `api/models/` |
| JSON 容错解析 | `_find_json_blocks()` 扫描平衡 `{...}` 块，反向尝试 | 所有 LLM 节点 |
| Dry-run 模式 | `TRADER_DRY_RUN=1` 只打印不下单 | `executor/` |

---

## 九、与 myTrader 现有架构的对比

| 维度 | 案例设计 | myTrader 现状 |
|------|---------|---------------|
| Agent 编排 | LangGraph StateGraph，显式节点+边 | FastAPI + Celery 任务，无显式图 |
| 人审机制 | `interrupt()` 硬卡点，checkpointer 持久化 | API endpoint 审批，无持久化恢复 |
| 风控层 | 8 条规则 + ATR 动态仓位 + 建议缩量 | 初步风控框架，规则待完善 |
| 技术信号 | MACD 回测 + 多因子共振矩阵 | 技术面扫描，尚无基本面融合 |
| 重试机制 | 条件边自动重试，最多 max_retry 次 | 无 |
| 审计日志 | 完整 state JSON 落盘 + `messages` 追加 | trade_logs 表，字段有限 |
| 定时调度 | APScheduler（与 LangGraph 深度集成）| 独立 scheduler 模块（YAML DAG）|

---

## 十、关键依赖

```
LangGraph>=0.2.50          # 核心框架
deepagents>=0.0.10         # Charles Agent 容器
dashscope>=1.20.0          # 通义千问 API
xtquant                    # 行情数据源（QMT）
pandas>=2.0.0
apscheduler>=3.10.0        # 定时调度
```
