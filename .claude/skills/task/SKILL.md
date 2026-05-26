# Task Skill

## 触发条件
- `/task` — 执行一个任务后停下，等待确认
- `/task all` — 连续执行所有 TODO 任务，直到队列空或遇到需确认的任务
- `/task archive` — 月末归档所有 DONE 条目

## 任务队列位置（可配置）

skill 启动时按以下优先级确定任务文件路径：

1. **读取项目 CLAUDE.md 中的 `TASK_FILE` 声明**（推荐方式）：
   在项目 CLAUDE.md 的"任务调度"或"工作规范"部分加一行：
   ```
   TASK_FILE=$HOME/Documents/notes/Daily/task/tasks_flow.md
   ```
   skill 会 Grep 当前项目的 CLAUDE.md，提取 `TASK_FILE=` 后面的值作为任务文件路径。

2. **Fallback**：若未配置，默认使用：
   ```
   $HOME/Documents/notes/Daily/task/tasks_myTrader.md
   ```

**归档路径**同样动态化：从 TASK_FILE 文件名（去掉 tasks_ 前缀和 .md 后缀）推导项目名。例如：
- `tasks_flow.md` → 归档到 `tasks_archive/flow-YYYY-MM.md`
- `tasks_myTrader.md` → 归档到 `tasks_archive/myTrader-YYYY-MM.md`

---

## 单次执行流程（/task）

### 步骤 0 - 确定任务文件

Grep 当前项目 CLAUDE.md，提取 `TASK_FILE=` 配置值。若找不到，使用 fallback 路径。在整个执行过程中使用该路径，后续步骤中的"任务文件"均指此处确定的路径。

**文件存在性检查**：路径确定后，尝试读取该文件。若文件不存在，立即输出并终止：
```
[ERROR] 任务文件不存在：<路径>
请创建该文件，或在 CLAUDE.md 中通过 TASK_FILE= 指定正确路径。
```

### 步骤 1 - 取任务

读取任务文件，取优先级最高的 [TODO]（P1 > P2 > P3，同级按顺序）。

无 [TODO] 时输出：
```
[QUEUE EMPTY] 队列为空，请在 <任务文件路径> 添加任务。
```

### 步骤 2 - 标记并告知

将该条目改为 `[DOING]`，输出：
```
[TASK] <标题> (P1/P2/P3)
描述：<描述>
验收：<验收条件>
```

### 步骤 3 - 自主执行

**不询问用户，直接执行。** 以下情况例外（暂停并说明原因）：
- 任务描述里明确写了"需确认"
- 涉及不可逆操作（删表、清数据、强制覆盖生产配置）
- 找不到关键文件且无法通过 Grep/Glob 定位

执行规则：
- Glob/Grep 定位文件，不猜路径
- 遵守 CLAUDE.md 所有 CRITICAL 规则
- 涉及 DB schema 变更：先输出改动列表再执行
- 涉及生产部署：走 /deploy 技能

有可自动验证的验收条件时执行：
```bash
python -m pytest <相关测试> -x -q 2>&1 | tail -5
```

### 步骤 4 - 更新队列（tasks 文件只记状态，不堆日志）

将条目移到"已完成任务"区，改为：
```
## [DONE] <标题>
优先级：P1/P2/P3
完成：<YYYY-MM-DD>
结果：<一句话，如 "pytest PASSED 12，commit abc1234" 或 "已部署，服务正常">
```

### 步骤 5 - 输出执行摘要（显示在 iTerm）

```
[DONE] <标题>
改动文件：<列表>
验收：<pytest PASSED N / 人工验收>
commit：<hash>
队列剩余：<N> 个 TODO
```

---

## 连续执行模式（/task all）

重复执行单次流程，每完成一个任务自动取下一个，直到：
- 队列为空 → 输出 `[QUEUE EMPTY] 全部任务已完成`
- 遇到需人工确认的任务 → 暂停，说明原因，等待指令

每个任务之间输出分隔线：
```
─────────────────────────────────────
[N/M] 完成：<上一个标题> → 开始：<下一个标题>
─────────────────────────────────────
```

---

## 月末归档（/task archive）

1. 按"步骤 0"确定任务文件路径，从文件名推导项目名（去掉 `tasks_` 前缀和 `.md` 后缀）
2. 读取任务文件中所有 [DONE] 条目
3. 若 `tasks_archive/` 目录不存在，自动创建（`mkdir -p`）
4. 追加写入 `$HOME/Documents/notes/Daily/task/tasks_archive/<项目名>-YYYY-MM.md`
5. 从任务文件删除这些条目
6. 输出：`归档 N 条 → tasks_archive/<项目名>-YYYY-MM.md，队列剩余 M 条 TODO`
