# Bug Fix Skill

## 触发条件
- 用户说 "/fix <bug描述>" 或 "帮我修 <bug描述>"
- 用户列出一个或多个 bug 要求修复

## 执行规则

**自主执行，不询问用户**。如果文件不在预期位置，用 Grep/Glob 定位，不要反复猜测。

每个 bug 独立走完以下 6 步后，再处理下一个 bug。

---

## 每个 Bug 的修复流程

### 步骤 1 - 理解现有行为
- 用 Glob/Grep 定位相关源文件，不要凭记忆猜文件名
- 读取相关文件，理解当前逻辑和出错路径
- 明确：触发 bug 的输入条件是什么？

### 步骤 2 - 写失败测试
- 在 `tests/` 下找到或创建对应测试文件
- 写一个能复现 bug 的测试函数，命名为 `test_<描述>_bug`
- 测试必须在修复前**失败**

### 步骤 3 - 确认测试失败
```bash
python -m pytest tests/<test_file>.py::test_<function_name> -x -v
```
- 确认输出显示 FAILED，否则重新审视测试逻辑

### 步骤 4 - 实现修复
- 最小化改动：只改导致 bug 的代码，不顺手重构周边
- 遵守 CLAUDE.md 的 CRITICAL 规则：
  - import 独立成行
  - SQL 字段与 VALUES 数量一致
  - 枚举大小写一致，作为 dict key 用 `.value`
  - 禁止 emoji

### 步骤 5 - 验证测试通过
```bash
python -m pytest tests/<test_file>.py -x -v
```
- 如果仍然失败，分析原因并迭代，直到通过为止
- 运行更宽泛的测试确认无回归：
```bash
python -m pytest tests/ -x -q
```

### 步骤 6 - 提交
每个 bug 单独一个 commit：
```
fix(<module>): <简洁描述修复内容>

<可选：说明根因和修复方式>

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
```

---

## 输出格式

每个 bug 修复完毕后输出：

```
### Bug N: <描述>
- 根因：<一句话>
- 修复文件：<file.py:行号>
- 测试：tests/<file>.py::<function_name>
- 状态：[FIXED]
```

最后输出总结：
```
## 修复总结
- Bug 1: [FIXED] / [PARTIAL] / [BLOCKED: 原因]
- Bug 2: [FIXED] / [PARTIAL] / [BLOCKED: 原因]
```
