# Code Review Skill

## 触发条件
- 用户请求 code review 或说 "/review"
- 用户说 "review 一下" / "看下改动" / "帮我 review"

## 执行步骤

### 1. 获取最新 diff（必须每次重新执行，禁止使用缓存）

```bash
git diff main...HEAD
```

如果当前就在 main 分支，改用：

```bash
git diff HEAD~1
```

### 2. 并行子智能体检查

用 Agent 工具启动 3 个并行子智能体，同时执行以下检查：

**Agent 1 - 逻辑审查**
- 分析每个改动文件的 bug 风险、边界条件、错误假设
- 重点检查：
  - [CRITICAL] 逻辑错误、空指针、类型不匹配、边界条件
  - [CRITICAL] 安全问题：SQL 注入、硬编码密钥、未鉴权接口
  - [WARN] 因子/数据：MA min_periods、交易日/自然日混淆、Decimal 未转 float
  - [WARN] 代码规范：import 合并、emoji 字符、output 路径不规范、枚举大小写

**Agent 2 - Lint / 代码风格**
- 对改动的 Python 文件运行：
  ```bash
  python -m flake8 <changed_files> --max-line-length=120 2>&1 | head -30
  ```
- 检查 CLAUDE.md 规范：import 独立成行、禁止裸 print、枚举 .value 用法
- 报告：文件:行号 - 问题描述

**Agent 3 - 测试覆盖**
- 识别改动代码路径中缺少测试覆盖的部分
- 列出需要新增的具体测试函数（格式：`tests/<file>.py::test_<name>`）
- 对已有 Python 测试文件运行：
  ```bash
  python -m pytest tests/ -x -q 2>&1 | tail -20
  ```
- 如有 TypeScript 改动，在 web/ 目录运行类型检查：
  ```bash
  cd web && npx tsc --noEmit --skipLibCheck 2>&1 | head -20
  ```

### 3. 汇总报告格式

等 3 个 Agent 都完成后，输出统一报告：

```
## Code Review: <branch 名> vs main

### 概要
<1-3 句话描述本次改动目的>

### [CRITICAL] 必须修复
- file.py:行号 - 问题描述（来源：逻辑/安全）

### [WARN] 建议修复
- file.py:行号 - 问题描述（来源：lint/规范/数据）

### [INFO] 可选优化
- 描述

### 测试缺口
- tests/<file>.py::test_<name> - 需要覆盖的场景

### Lint 问题
- file.py:行号 - flake8 错误码 + 描述

### 测试运行结果
- pytest: <PASSED N / FAILED N>
- tsc: <OK / N errors>

### 结论
[PASS / PASS with warnings / BLOCK] - 一句话总结
```

### 4. 多轮 review（同一会话）

本技能支持在**同一会话**中多轮审查，无需重新启动：

**触发词**：用户说 "review again" / "再看一次" / "我改好了" 时，进入二次审查模式。

执行步骤（必须严格遵守）：
1. 重新运行 `git diff main...HEAD` 获取**最新** diff（禁止使用会话中任何缓存结果）
2. 重新启动 3 个并行 Agent 执行完整检查
3. 对比本会话上一轮的 review 结论，明确列出三类变化：
   - [FIXED] 已修复的问题（逐条列出）
   - [REMAIN] 仍未修复的问题（逐条列出）
   - [NEW] 新引入的问题（逐条列出）
4. 更新结论：[PASS / PASS with warnings / BLOCK]

**目的**：避免跨会话丢失上下文、避免第二次 review 漏检新改动。
