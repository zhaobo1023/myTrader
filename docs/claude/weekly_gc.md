# Weekly Garbage Collection SOP

项目：myTrader
维护人：zhaobo
最后更新：2026-04-21

---

## 目标

1. 把 AI 智能体产出的系统性问题转化为永久性约束（lint 规则 / 测试断言 / 文档），而非口头提醒。
2. 减少下周同类问题的发生频率，做到"一次修复，永久生效"。
3. 单次 GC 不超过 2 小时，保持可持续执行。

---

## 触发条件

- [定期] 每周五下班前 1 小时，固定执行。
- [即时] 智能体在本周内连续 3 次犯同类错误时，立即触发，不等到周五。

---

## 执行步骤（SOP）

### Step 1 — 收集问题（5 分钟）

扫描本周以下来源，整理出重复性问题：

- git log 中的 fix/hotfix commit 信息
- code review 评论（PR comments）
- CLAUDE.md 中"Bug 修复记录"章节的新增条目
- 与智能体对话中人工纠正过的操作

将问题填入下方"问题记录模板"表格。

### Step 2 — 分类（10 分钟）

对每个问题打分类标签：

- A = 可写成 lint/pre-commit 规则（可自动检测的代码模式）
- B = 可写成测试断言（可通过 pytest/单测验证的行为）
- C = 只能写文档（依赖上下文判断，无法自动化检测）

### Step 3 — 处理（主要时间，60-90 分钟）

**A 类 — 写或更新 pre-commit hook**

- 在 `.pre-commit-config.yaml` 或 `scripts/hooks/` 中新增/修改规则。
- 常见场景：emoji 字符检测、import 语法格式、SQL 逗号缺失等。
- 更新后在"处理方式"列记录 hook 名称和检测逻辑摘要。

**B 类 — 在 tests/ 下新增测试断言**

- 优先放入 `tests/unit/` 目录，文件名前缀 `test_gc_` 以便识别来源。
- 测试应覆盖具体的边界场景，而非泛化测试。
- 更新后在"处理方式"列记录测试文件路径和测试函数名。

**C 类 — 更新 CLAUDE.md 或领域文档**

- 属于"代码规范与常见 Bug 注意事项"的，更新 `/Users/zhaobo/data0/person/myTrader/CLAUDE.md` 对应章节。
- 属于特定模块的，更新 `docs/` 下对应的领域文档。
- 更新后在"处理方式"列记录文件路径和章节标题。

### Step 4 — 验证（10 分钟）

```bash
# 验证 pre-commit 规则全部通过
pre-commit run --all-files

# 运行单元测试，确认新增断言不破坏现有用例
pytest tests/unit/ -v --tb=short
```

[OK] 两项均通过后进入 Step 5。
[WARN] 若有失败，在当次 GC 内修复，不留尾巴。

### Step 5 — 提交

```bash
git add .
git commit -m "chore(gc): weekly garbage collection $(date +%Y-%m-%d)"
```

commit message 格式固定，便于后续用 `git log --grep="chore(gc)"` 检索所有 GC 记录。

---

## 问题记录模板

每次 GC 新开一行，不删除历史记录。

| 日期 | 问题描述 | 分类(A/B/C) | 处理方式 | 状态 |
|------|----------|-------------|----------|------|
|      |          |             |          |      |

状态可选值：[TODO] / [IN_PROGRESS] / [DONE] / [WONT_FIX]

---

## 历史记录

<!-- 按周填写，格式：### YYYY-WXX (YYYY-MM-DD) -->

<!-- 示例（删除后按实际填写）：
### 2026-W17 (2026-04-24)
- 问题数：3
- A 类：1（新增 emoji 检测 hook）
- B 类：1（新增 SQL 逗号缺失断言）
- C 类：1（更新 CLAUDE.md import 规范章节）
- 耗时：45 分钟
-->

---

## 备注

本文档本身是"面包屑"。

智能体（Claude Code）在执行任务过程中，若发现以下情况，应主动在回复末尾提醒人类触发 GC：

- 同一类错误在本次任务中出现 2 次及以上（如多处 import 语法错误、多处 SQL 逗号缺失）
- 人工纠正了智能体的操作，且该操作模式可被规则化
- 修复了一个此前已在 CLAUDE.md 中记录过的同类 Bug

提醒格式：

```
[GC_HINT] 本次任务中出现了 X 类系统性问题（描述），建议在周五 GC 时将其转化为 lint 规则 / 测试断言 / 文档更新。
```
