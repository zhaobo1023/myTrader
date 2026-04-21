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

### 2. 分析维度

按以下顺序逐一检查：

- **[CRITICAL] Bug 风险**：逻辑错误、边界条件、空指针、类型不匹配
- **[CRITICAL] 安全问题**：SQL 注入、硬编码密钥、未鉴权接口
- **[WARN] 代码规范**：import 合并、emoji 字符、output 路径不规范、枚举大小写
- **[WARN] 因子/数据问题**：MA min_periods、交易日/自然日混淆、Decimal 未转 float
- **[INFO] 可读性**：命名、注释缺失、函数过长（>100行）
- **[INFO] 测试覆盖**：新逻辑是否有对应测试

### 3. 输出格式

```
## Code Review: <branch 名> vs main

### 概要
<1-3 句话描述本次改动目的>

### [CRITICAL] 必须修复
- file.py:行号 - 问题描述

### [WARN] 建议修复
- file.py:行号 - 问题描述

### [INFO] 可选优化
- 描述

### 测试建议
- 需要补充的测试场景

### 结论
[PASS / PASS with warnings / BLOCK] - 一句话总结
```

### 4. 多轮 review（同一会话）

本技能支持在**同一会话**中多轮审查，无需重新启动：

**触发词**：用户说 "review again" / "再看一次" / "我改好了" 时，进入二次审查模式。

执行步骤（必须严格遵守）：
1. 重新运行 `git diff main...HEAD` 获取**最新** diff（禁止使用会话中任何缓存结果）
2. 对比本会话上一轮的 review 结论，明确列出三类变化：
   - [FIXED] 已修复的问题（逐条列出）
   - [REMAIN] 仍未修复的问题（逐条列出）
   - [NEW] 新引入的问题（逐条列出）
3. 更新结论：[PASS / PASS with warnings / BLOCK]

**目的**：避免跨会话丢失上下文、避免第二次 review 漏检新改动。
