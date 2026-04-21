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

### 4. 二次 review

如果本次是重新 review（用户已修改过代码），必须：
1. 重新运行 `git diff main...HEAD` 获取最新 diff
2. 对比上次 review 结论，明确列出：
   - 已修复的问题
   - 仍未修复的问题
   - 新增的问题
