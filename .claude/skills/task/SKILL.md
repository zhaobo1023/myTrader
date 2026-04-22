# Task Skill

## 触发条件
- 用户说 "/task" 或 "取下一个任务" 或 "继续"

## 任务队列位置
/Users/zhaobo/Documents/notes/Finance/投研系统设计/tasks.md

---

## 执行流程

### 步骤 1 - 读取队列，取最高优先级任务

读取 tasks.md，找到第一个 [TODO] 条目（P1 优先于 P2 优先于 P3）。

如果没有 [TODO]，输出：
```
[QUEUE EMPTY] 任务队列为空，请在 tasks.md 中添加新任务。
```
然后停止。

### 步骤 2 - 确认任务

输出任务摘要，格式：
```
## 取到任务：<标题>
- 优先级：<P1/P2/P3>
- 描述：<描述>
- 验收：<验收条件>

开始执行...
```

将 tasks.md 中该条目的 `[TODO]` 改为 `[DOING]`。

### 步骤 3 - 执行任务

**自主执行，不询问用户**（除非任务描述明确说需要确认）。

执行规则：
- 用 Glob/Grep 定位文件，不猜文件名
- 遵守 CLAUDE.md 的所有 CRITICAL 规则
- 涉及数据库 schema 变更，先列改动再执行
- 涉及生产部署，使用 /deploy 技能

如果任务有验收条件且可自动验证（pytest / 语法检查），执行验证：
```bash
python -m pytest <相关测试> -x -q
```

### 步骤 4 - 完成，更新队列

将 tasks.md 中该条目改为 `[DONE]`，并追加完成信息：
```
## [DONE] <标题>
优先级：<P1/P2/P3>
描述：<原描述>
验收：<原验收>
完成时间：<YYYY-MM-DD>
结果：<一句话说明实际做了什么，或测试结果>
```

将条目移动到 tasks.md 的"已完成任务"区域。

### 步骤 5 - 报告

输出执行摘要：
```
## 任务完成：<标题>
- 状态：[DONE]
- 改动文件：<列表>
- 验收结果：<pytest PASSED N / 人工验收>
- commit：<commit hash 或 "未提交">

队列剩余：<N> 个 TODO 任务
说 "/task" 继续取下一个。
```

---

## 月末归档（说 "/task archive" 触发）

1. 读取 tasks.md 中所有 [DONE] 条目
2. 写入 tasks_archive/YYYY-MM.md（追加，文件头注明归档时间）
3. 从 tasks.md 中删除这些条目
4. 输出：归档了 N 条，tasks.md 当前剩余 M 条 TODO
